"""
SAP Flat File Ingestion Parser

Decision: We handle SAP's MM (Materials Management) flat file export — specifically the
MIGO/EKBE format that procurement and fuel teams typically export via SE16 or custom reports.

This is the most common export a sustainability lead would actually receive:
a tab-separated or semicolon-delimited file exported from SAP GUI, often with German headers
depending on the SAP system locale.

We do NOT handle IDocs (too complex for a prototype, requires EDI infrastructure),
OData (requires live SAP connectivity), or BAPIs (requires RFC). Justified in DECISIONS.md.

Realistic SAP fuel/procurement export columns we handle:
  MANDT   - Client (mandant) - multi-tenant SAP concept
  WERKS   - Plant code (4-char, meaningless without lookup)
  MATNR   - Material number
  MAKTX   - Material description (sometimes German: "Dieselkraftstoff")
  MENGE   - Quantity
  MEINS   - Unit of measure (SAP internal: L, KG, M3, GAL, etc.)
  BUDAT   - Posting date (YYYYMMDD — SAP standard)
  LIFNR   - Vendor number
  BELNR   - Document number (our source_row_id)
  DMBTR   - Amount in local currency
  WAERS   - Currency
  KOSTL   - Cost centre
  BWART   - Movement type (201=goods issue, 261=consumption for order)
"""

import csv
import io
import decimal
from datetime import datetime, date
from typing import Optional
from django.conf import settings


# SAP unit of measure → our normalised unit + conversion factor to litres or kg
SAP_UNIT_MAP = {
    'L':   ('litre', decimal.Decimal('1')),
    'LTR': ('litre', decimal.Decimal('1')),
    'GAL': ('litre', decimal.Decimal('3.78541')),   # US gallon
    'KG':  ('kg', decimal.Decimal('1')),
    'TO':  ('kg', decimal.Decimal('1000')),         # metric tonne
    'M3':  ('litre', decimal.Decimal('1000')),      # cubic metre
    'ST':  ('unit', decimal.Decimal('1')),          # Stück = piece
}

# Material description keywords → emission category
MATERIAL_CATEGORY_MAP = {
    'diesel': 'fuel_diesel',
    'dieselkraftstoff': 'fuel_diesel',
    'petrol': 'fuel_petrol',
    'benzin': 'fuel_petrol',
    'gasoline': 'fuel_petrol',
    'natural gas': 'fuel_natural_gas',
    'erdgas': 'fuel_natural_gas',
    'lpg': 'fuel_natural_gas',
}

EMISSION_FACTORS = {
    'fuel_diesel': (decimal.Decimal(str(settings.EMISSION_FACTORS['diesel_litre'])), 'DEFRA 2023', 'litre'),
    'fuel_petrol': (decimal.Decimal(str(settings.EMISSION_FACTORS['petrol_litre'])), 'DEFRA 2023', 'litre'),
    'fuel_natural_gas': (decimal.Decimal(str(settings.EMISSION_FACTORS['natural_gas_kwh'])), 'DEFRA 2023', 'kWh'),
}

# Plant code → location lookup (in production this would be a DB table)
PLANT_LOOKUP = {
    'IN01': 'Mumbai, India',
    'IN02': 'Delhi, India',
    'IN03': 'Bangalore, India',
    'DE01': 'Frankfurt, Germany',
    'US01': 'Houston, USA',
}


def parse_sap_date(date_str: str) -> Optional[date]:
    """SAP dates come as YYYYMMDD, DD.MM.YYYY, or DD/MM/YYYY."""
    date_str = date_str.strip()
    for fmt, note in [
        ('%Y%m%d', 'SAP YYYYMMDD'),
        ('%d.%m.%Y', 'European DD.MM.YYYY'),
        ('%d/%m/%Y', 'DD/MM/YYYY'),
        ('%Y-%m-%d', 'ISO'),
    ]:
        try:
            return datetime.strptime(date_str, fmt).date(), note
        except ValueError:
            continue
    return None, f"Unparseable date: {date_str!r}"


def detect_delimiter(content: str) -> str:
    """SAP exports use tab or semicolon depending on locale settings."""
    sample = content[:2000]
    if sample.count('\t') > sample.count(';'):
        return '\t'
    return ';'


def normalise_german_header(header: str) -> str:
    """Some SAP systems export German column names. Map known ones."""
    german_map = {
        'MENGE': 'MENGE',
        'BUCHUNGSDATUM': 'BUDAT',
        'WERK': 'WERKS',
        'MATERIAL': 'MATNR',
        'MATERIALBEZEICHNUNG': 'MAKTX',
        'EINHEIT': 'MEINS',
        'BELEGNUMMER': 'BELNR',
        'KOSTENSTELLE': 'KOSTL',
    }
    return german_map.get(header.upper().strip(), header.upper().strip())


def parse_sap_file(file_content: bytes, batch) -> list[dict]:
    """
    Parse a SAP flat file export and return a list of dicts ready to create EmissionRecord rows.
    Returns (records, errors) tuple.
    """
    from apps.emissions.models import EmissionRecord

    text = file_content.decode('utf-8-sig', errors='replace')  # Handle BOM from SAP exports
    delimiter = detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    records = []
    errors = []

    for i, row in enumerate(reader, start=2):
        # Normalise headers
        row = {normalise_german_header(k): v.strip() for k, v in row.items()}

        try:
            # --- Material / category detection ---
            description = row.get('MAKTX', row.get('MATNR', '')).lower()
            category = None
            for keyword, cat in MATERIAL_CATEGORY_MAP.items():
                if keyword in description:
                    category = cat
                    break

            if not category:
                errors.append({
                    'row': i,
                    'error': f"Cannot classify material: {description!r}. Skipping.",
                    'raw': dict(row),
                })
                continue

            # --- Quantity & unit ---
            raw_quantity = row.get('MENGE', '0').replace(',', '.').strip()
            try:
                quantity = decimal.Decimal(raw_quantity)
            except decimal.InvalidOperation:
                errors.append({'row': i, 'error': f"Invalid quantity: {raw_quantity!r}", 'raw': dict(row)})
                continue

            sap_unit = row.get('MEINS', 'L').upper().strip()
            unit_info = SAP_UNIT_MAP.get(sap_unit)
            if not unit_info:
                errors.append({'row': i, 'error': f"Unknown SAP unit: {sap_unit!r}", 'raw': dict(row)})
                continue

            normalised_unit, conversion_factor = unit_info
            converted_quantity = quantity * conversion_factor
            unit_converted = conversion_factor != decimal.Decimal('1')

            # --- Date ---
            activity_date, date_note = parse_sap_date(row.get('BUDAT', ''))
            if not activity_date:
                errors.append({'row': i, 'error': date_note, 'raw': dict(row)})
                continue

            # --- Emission factor ---
            ef, ef_source, ef_unit = EMISSION_FACTORS[category]

            # --- Suspicious flag ---
            is_flagged = False
            flag_reason = ''
            if converted_quantity > 100000:
                is_flagged = True
                flag_reason = f"Unusually large quantity: {converted_quantity} {normalised_unit}"

            plant = row.get('WERKS', '')
            plant_location = PLANT_LOOKUP.get(plant, f"Unknown plant: {plant}")

            records.append({
                'scope': 1,
                'category': category,
                'activity_date': activity_date,
                'activity_quantity': converted_quantity,
                'activity_unit': normalised_unit,
                'activity_description': f"{row.get('MAKTX', description)} | Plant: {plant_location} | Vendor: {row.get('LIFNR', 'N/A')} | Cost centre: {row.get('KOSTL', 'N/A')}",
                'emission_factor': ef,
                'emission_factor_source': ef_source,
                'co2e_kg': converted_quantity * ef,
                'source_system': 'SAP ECC / Flat File Export',
                'source_row_id': row.get('BELNR', f'row_{i}'),
                'raw_data': dict(row),
                'unit_conversion_applied': unit_converted,
                'unit_conversion_note': f"SAP unit {sap_unit} × {conversion_factor} → {normalised_unit}" if unit_converted else '',
                'date_parse_note': date_note,
                'is_flagged': is_flagged,
                'flag_reason': flag_reason,
                'batch': batch,
                'organisation': batch.organisation,
                'review_status': 'pending',
            })

        except Exception as e:
            errors.append({'row': i, 'error': str(e), 'raw': dict(row)})

    return records, errors
