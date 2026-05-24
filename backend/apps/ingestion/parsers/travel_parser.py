"""
Corporate Travel Ingestion Parser

Decision: We ingest a JSON export format modelled on Navan's trip export and Concur's
Travel Itinerary API response. Both platforms expose similar data structures.

Why JSON over CSV for travel?
- Travel data is inherently nested: one trip has multiple legs (flights), hotels, car rentals
- Navan's export and Concur's TripIt integration both use JSON
- CSV flattening loses the leg-level detail needed for accurate emission factors

Key complications handled:
1. Flights: emission factor depends on cabin class and distance
   - Distance not always given; sometimes only origin/destination airport codes
   - We use a haversine approximation from IATA airport coordinates
2. Hotels: emission factor is per room-night, not per distance
3. Ground transport: car rental (per km) vs taxi/rideshare (per km) vs rail (per km)

Emission categories:
  Flight domestic (<500km):    Scope 3 - flight_domestic
  Flight short haul (<3000km): Scope 3 - flight_short_haul
  Flight long haul (>3000km):  Scope 3 - flight_long_haul
  Hotel stay:                  Scope 3 - hotel_stay
  Ground transport:            Scope 3 - ground_transport
"""

import decimal
import math
from datetime import datetime, date
from django.conf import settings


# ---- Airport coordinate lookup (subset of IATA airports) ----
# In production this would be a DB table populated from OurAirports dataset
AIRPORT_COORDS = {
    'BLR': (13.1979, 77.7063),  'DEL': (28.5665, 77.1031),
    'BOM': (19.0896, 72.8656),  'MAA': (12.9900, 80.1693),
    'CCU': (22.6520, 88.4463),  'HYD': (17.2403, 78.4294),
    'LHR': (51.4775, -0.4614),  'CDG': (49.0097, 2.5479),
    'FRA': (50.0379, 8.5622),   'AMS': (52.3086, 4.7639),
    'DXB': (25.2532, 55.3657),  'SIN': (1.3644, 103.9915),
    'JFK': (40.6413, -73.7781), 'ORD': (41.9742, -87.9073),
    'LAX': (33.9425, -118.4081),'SFO': (37.6213, -122.3790),
    'NRT': (35.7653, 140.3856), 'ICN': (37.4602, 126.4407),
    'SYD': (-33.9399, 151.1753),'DOH': (25.2731, 51.6081),
}

EF = settings.EMISSION_FACTORS


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def classify_flight(distance_km: float) -> tuple[str, decimal.Decimal, str]:
    """Returns (category, emission_factor, ef_source)"""
    if distance_km < 500:
        return 'flight_domestic', decimal.Decimal(str(EF['flight_economy_km'])), 'DEFRA 2023 (domestic)'
    elif distance_km < 3000:
        return 'flight_short_haul', decimal.Decimal(str(EF['flight_economy_km'])), 'DEFRA 2023 (short-haul)'
    else:
        return 'flight_long_haul', decimal.Decimal(str(EF['flight_economy_km'])), 'DEFRA 2023 (long-haul)'


def parse_date(val: str) -> date:
    if not val or val == 'None':
        raise ValueError(f"Empty date value")
    val = str(val).strip()
    for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
        try:
            return datetime.strptime(val, fmt).date()
        except (ValueError, TypeError):
            continue
    # Try truncating to date part
    if len(val) > 10:
        try:
            return datetime.strptime(val[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
    raise ValueError(f"Cannot parse date: {val!r}")


def parse_travel_json(data, batch) -> tuple[list[dict], list[dict]]:
    """
    Accepts either:
    - A list of trip objects (Navan bulk export)
    - A dict with a 'trips' key
    """
    if isinstance(data, dict):
        trips = data.get('trips', data.get('data', [data]))
    else:
        trips = data

    records = []
    errors = []

    for trip_idx, trip in enumerate(trips):
        trip_id = trip.get('id', trip.get('trip_id', f'trip_{trip_idx}'))
        traveller = trip.get('traveller', trip.get('employee_name', 'Unknown'))
        department = trip.get('department', trip.get('cost_centre', ''))

        segments = trip.get('segments', trip.get('legs', trip.get('items', [])))

        for seg_idx, seg in enumerate(segments):
            seg_type = (seg.get('type') or seg.get('segment_type') or '').lower()
            row_id = f"{trip_id}_seg_{seg_idx}"

            try:
                if seg_type in ('flight', 'air'):
                    rec = _parse_flight(seg, trip_id, traveller, department, batch, row_id)
                    if rec:
                        records.append(rec)
                    else:
                        errors.append({'trip': trip_id, 'seg': seg_idx, 'error': 'Cannot resolve airport coordinates', 'raw': seg})

                elif seg_type in ('hotel', 'accommodation', 'lodging'):
                    rec = _parse_hotel(seg, trip_id, traveller, department, batch, row_id)
                    records.append(rec)

                elif seg_type in ('car', 'car_rental', 'ground', 'taxi', 'rail', 'train'):
                    rec = _parse_ground(seg, trip_id, traveller, department, batch, row_id)
                    if rec:
                        records.append(rec)
                    else:
                        errors.append({'trip': trip_id, 'seg': seg_idx, 'error': 'No distance or duration for ground transport', 'raw': seg})

                else:
                    errors.append({'trip': trip_id, 'seg': seg_idx, 'error': f"Unknown segment type: {seg_type!r}", 'raw': seg})

            except Exception as e:
                errors.append({'trip': trip_id, 'seg': seg_idx, 'error': str(e), 'raw': seg})

    return records, errors


def _parse_flight(seg: dict, trip_id: str, traveller: str, dept: str, batch, row_id: str):
    origin = (seg.get('origin') or seg.get('from') or seg.get('departure_airport') or '').upper()
    dest = (seg.get('destination') or seg.get('to') or seg.get('arrival_airport') or '').upper()
    cabin = (seg.get('cabin') or seg.get('class') or 'economy').lower()

    # Distance: use provided distance, else compute from airport coords
    distance_km = seg.get('distance_km') or seg.get('distance')
    dist_note = ''
    is_flagged = False
    flag_reason = ''

    if not distance_km:
        orig_coords = AIRPORT_COORDS.get(origin)
        dest_coords = AIRPORT_COORDS.get(dest)
        if not orig_coords or not dest_coords:
            return None
        distance_km = haversine_km(*orig_coords, *dest_coords)
        dist_note = f"Distance estimated via haversine ({origin}→{dest}): {distance_km:.0f} km"
        is_flagged = True
        flag_reason = dist_note
    else:
        distance_km = float(distance_km)
        dist_note = f"Distance provided by source: {distance_km} km"

    category, ef, ef_source = classify_flight(distance_km)

    # Business class multiplier
    if 'business' in cabin or 'first' in cabin:
        ef = decimal.Decimal(str(EF['flight_business_km']))
        ef_source += ' (business class)'

    passengers = int(seg.get('passengers', seg.get('travellers', 1)))
    total_distance = decimal.Decimal(str(distance_km)) * passengers
    co2e = total_distance * ef

    dep_date_raw = seg.get('departure_date') or seg.get('date') or seg.get('depart_at', '')
    activity_date = parse_date(str(dep_date_raw))

    return {
        'scope': 3,
        'category': category,
        'activity_date': activity_date,
        'activity_quantity': total_distance,
        'activity_unit': 'passenger-km',
        'activity_description': f"Flight {origin}→{dest} | {cabin.title()} | {passengers} pax | Traveller: {traveller} | Dept: {dept}",
        'emission_factor': ef,
        'emission_factor_source': ef_source,
        'co2e_kg': co2e,
        'source_system': 'Navan / Corporate Travel Platform',
        'source_row_id': row_id,
        'raw_data': seg,
        'unit_conversion_applied': True,
        'unit_conversion_note': dist_note,
        'date_parse_note': '',
        'is_flagged': is_flagged,
        'flag_reason': flag_reason,
        'batch': batch,
        'organisation': batch.organisation,
        'review_status': 'pending',
    }


def _parse_hotel(seg: dict, trip_id: str, traveller: str, dept: str, batch, row_id: str):
    nights = int(seg.get('nights') or seg.get('duration_nights') or 1)
    hotel_name = seg.get('hotel_name') or seg.get('property') or 'Unknown hotel'
    city = seg.get('city') or seg.get('location') or ''
    check_in_raw = seg.get('check_in') or seg.get('date') or ''
    activity_date = parse_date(str(check_in_raw))

    ef = decimal.Decimal(str(EF['hotel_night']))
    co2e = ef * nights

    return {
        'scope': 3,
        'category': 'hotel_stay',
        'activity_date': activity_date,
        'activity_quantity': decimal.Decimal(str(nights)),
        'activity_unit': 'room-nights',
        'activity_description': f"Hotel: {hotel_name} | {city} | {nights} nights | Traveller: {traveller}",
        'emission_factor': ef,
        'emission_factor_source': 'DEFRA 2023 (hotel, average)',
        'co2e_kg': co2e,
        'source_system': 'Navan / Corporate Travel Platform',
        'source_row_id': row_id,
        'raw_data': seg,
        'unit_conversion_applied': False,
        'unit_conversion_note': '',
        'date_parse_note': '',
        'is_flagged': False,
        'flag_reason': '',
        'batch': batch,
        'organisation': batch.organisation,
        'review_status': 'pending',
    }


def _parse_ground(seg: dict, trip_id: str, traveller: str, dept: str, batch, row_id: str):
    distance_km = seg.get('distance_km') or seg.get('distance')
    if not distance_km:
        return None

    distance_km = decimal.Decimal(str(distance_km))
    transport_type = (seg.get('type') or seg.get('vehicle_type') or 'car').lower()
    date_raw = seg.get('date') or seg.get('pickup_date') or ''
    activity_date = parse_date(str(date_raw))

    ef = decimal.Decimal(str(EF['car_rental_km']))
    ef_source = 'DEFRA 2023 (average car)'
    co2e = distance_km * ef

    return {
        'scope': 3,
        'category': 'ground_transport',
        'activity_date': activity_date,
        'activity_quantity': distance_km,
        'activity_unit': 'km',
        'activity_description': f"Ground: {transport_type.title()} | {distance_km} km | Traveller: {traveller}",
        'emission_factor': ef,
        'emission_factor_source': ef_source,
        'co2e_kg': co2e,
        'source_system': 'Navan / Corporate Travel Platform',
        'source_row_id': row_id,
        'raw_data': seg,
        'unit_conversion_applied': False,
        'unit_conversion_note': '',
        'date_parse_note': '',
        'is_flagged': False,
        'flag_reason': '',
        'batch': batch,
        'organisation': batch.organisation,
        'review_status': 'pending',
    }
