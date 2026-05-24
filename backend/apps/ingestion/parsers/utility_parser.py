"""
Utility Data Ingestion Parser

Decision: We handle utility portal CSV exports — the format that BESCOM (Bangalore), 
MSEDCL (Mumbai), and similar Indian state DISCOMs export from their consumer portals.
We also handle the generic Green Button Data format used by US/UK utilities.

Why CSV over PDF or API?
- PDF parsing requires OCR and is brittle across utility formats (100+ in India alone)
- Utility APIs exist (Green Button API, ESPI standard) but <20% of Indian DISCOMs offer them
- CSV portal exports are the most common real-world deliverable from a facilities manager

Realistic utility CSV columns:
  Account Number      - consumer number / service account
  Meter Number        - meter ID (may have multiple meters per account)
  Billing Period From - start of billing cycle
  Billing Period To   - end of billing cycle
  Reading Date        - actual meter reading date
  Previous Reading    - kWh at start
  Current Reading     - kWh at end
  Units Consumed      - kWh consumed (sometimes MWh or kVAh — watch out)
  Unit                - kWh / MWh / kVAh
  Peak Units          - ToD tariff peak units (optional)
  Off Peak Units      - ToD tariff off-peak units (optional)
  Amount              - bill amount in local currency
  Currency            - INR / GBP / USD
  Tariff Code         - HT/LT/commercial/industrial
  Location/Site       - facility name or address

Key complications:
  - Billing periods don't align with calendar months
  - kVAh ≠ kWh (apparent energy vs real energy); we store kVAh but flag it
  - Some exports use MWh; we convert to kWh
  - Some utilities export cumulative meter readings, not consumption
"""

import csv
import io
import decimal
from datetime import datetime, date
from typing import Optional
from django.conf import settings


ELECTRICITY_EF = decimal.Decimal(str(settings.EMISSION_FACTORS['electricity_kwh_india']))
ELECTRICITY_EF_SOURCE = 'CEA India Grid Emission Factor 2023'

UNIT_CONVERSION = {
    'KWH': decimal.Decimal('1'),
    'MWH': decimal.Decimal('1000'),
    'KVAH': None,  # kVAh: flag, store as-is (apparent energy, not directly comparable)
    'UNITS': decimal.Decimal('1'),  # "Units" == kWh in Indian utility context
}

HEADER_ALIASES = {
    'account number': 'account_number',
    'account no': 'account_number',
    'consumer no': 'account_number',
    'service account': 'account_number',
    'meter number': 'meter_number',
    'meter no': 'meter_number',
    'billing period from': 'period_from',
    'from date': 'period_from',
    'billing period to': 'period_to',
    'to date': 'period_to',
    'reading date': 'reading_date',
    'units consumed': 'units_consumed',
    'consumption': 'units_consumed',
    'kwh consumed': 'units_consumed',
    'energy consumed': 'units_consumed',
    'unit': 'unit',
    'units': 'unit',
    'uom': 'unit',
    'amount': 'amount',
    'bill amount': 'amount',
    'location': 'location',
    'site': 'location',
    'facility': 'location',
    'tariff code': 'tariff_code',
    'tariff': 'tariff_code',
}


def normalise_header(h: str) -> str:
    return HEADER_ALIASES.get(h.lower().strip(), h.lower().strip().replace(' ', '_'))


def parse_date(val: str) -> tuple[Optional[date], str]:
    val = val.strip()
    for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y', '%d %b %Y', '%d-%b-%Y']:
        try:
            return datetime.strptime(val, fmt).date(), f"Parsed with format {fmt}"
        except ValueError:
            continue
    return None, f"Cannot parse date: {val!r}"


def parse_utility_file(file_content: bytes, batch) -> tuple[list[dict], list[dict]]:
    text = file_content.decode('utf-8-sig', errors='replace')

    # Detect delimiter
    sample = text[:2000]
    delimiter = ',' if sample.count(',') >= sample.count(';') else ';'

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    records = []
    errors = []

    for i, row in enumerate(reader, start=2):
        row = {normalise_header(k): v.strip() for k, v in row.items() if k}

        try:
            # Quantity
            raw_qty = row.get('units_consumed', '0').replace(',', '').strip()
            if not raw_qty:
                errors.append({'row': i, 'error': 'Empty units consumed', 'raw': dict(row)})
                continue
            try:
                quantity = decimal.Decimal(raw_qty)
            except decimal.InvalidOperation:
                errors.append({'row': i, 'error': f"Invalid quantity: {raw_qty!r}", 'raw': dict(row)})
                continue

            if quantity <= 0:
                errors.append({'row': i, 'error': f"Non-positive consumption: {quantity}", 'raw': dict(row)})
                continue

            # Unit
            raw_unit = row.get('unit', 'kWh').upper().strip() or 'KWH'
            conversion = UNIT_CONVERSION.get(raw_unit)
            unit_note = ''
            is_flagged = False
            flag_reason = ''

            if raw_unit == 'KVAH':
                # kVAh: apparent energy, can't directly compute CO2e without power factor
                is_flagged = True
                flag_reason = 'Unit is kVAh (apparent energy). Power factor needed for accurate kWh conversion. Assumed PF=0.9 for estimate.'
                quantity = quantity * decimal.Decimal('0.9')
                normalised_unit = 'kWh (estimated from kVAh @ PF=0.9)'
                unit_note = flag_reason
            elif conversion is None:
                errors.append({'row': i, 'error': f"Unknown unit: {raw_unit!r}", 'raw': dict(row)})
                continue
            else:
                converted_quantity = quantity * conversion
                unit_converted = conversion != decimal.Decimal('1')
                normalised_unit = 'kWh'
                unit_note = f"{raw_unit} × {conversion} → kWh" if unit_converted else ''
                quantity = converted_quantity

            # Suspicious: unusually high monthly consumption
            if quantity > 500000:
                is_flagged = True
                flag_reason += f" | Very high consumption: {quantity} kWh. Verify meter reading."

            # Date: prefer reading_date, fall back to period_to
            date_val = row.get('reading_date') or row.get('period_to') or row.get('period_from', '')
            activity_date, date_note = parse_date(date_val)
            if not activity_date:
                errors.append({'row': i, 'error': date_note, 'raw': dict(row)})
                continue

            location = row.get('location') or row.get('site') or row.get('facility', 'Unknown site')
            meter = row.get('meter_number', 'N/A')
            account = row.get('account_number', 'N/A')
            tariff = row.get('tariff_code', 'N/A')

            co2e = quantity * ELECTRICITY_EF

            records.append({
                'scope': 2,
                'category': 'electricity',
                'activity_date': activity_date,
                'activity_quantity': quantity,
                'activity_unit': normalised_unit,
                'activity_description': f"Electricity | {location} | Meter: {meter} | Account: {account} | Tariff: {tariff}",
                'emission_factor': ELECTRICITY_EF,
                'emission_factor_source': ELECTRICITY_EF_SOURCE,
                'co2e_kg': co2e,
                'source_system': 'Utility Portal CSV Export',
                'source_row_id': f"{account}_{meter}_{date_val}",
                'raw_data': dict(row),
                'unit_conversion_applied': raw_unit != 'KWH',
                'unit_conversion_note': unit_note,
                'date_parse_note': date_note,
                'is_flagged': is_flagged,
                'flag_reason': flag_reason.strip(' |'),
                'batch': batch,
                'organisation': batch.organisation,
                'review_status': 'pending',
            })

        except Exception as e:
            errors.append({'row': i, 'error': str(e), 'raw': dict(row)})

    return records, errors
