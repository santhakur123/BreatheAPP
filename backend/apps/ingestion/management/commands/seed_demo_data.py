"""
Management command: python manage.py seed_demo_data

Creates a demo organisation, analyst user, and ingests sample data for all 3 sources.
Run after migrations.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from apps.emissions.models import Organisation, OrganisationMembership, IngestionBatch, EmissionRecord
from apps.ingestion.parsers.sap_parser import parse_sap_file
from apps.ingestion.parsers.utility_parser import parse_utility_file
from apps.ingestion.parsers.travel_parser import parse_travel_json
from django.db import transaction
import json


SAP_SAMPLE = """BELNR\tBUDAT\tWERKS\tMAKTX\tMENGE\tMEINS\tLIFNR\tKOSTL\tDMBTR\tWAERS
5000012345\t20240115\tIN01\tDiesel Kraftstoff\t4500.000\tL\tVEND001\tCC-OPS-01\t315000.00\tINR
5000012346\t20240118\tIN02\tDiesel Kraftstoff\t3200.500\tL\tVEND001\tCC-OPS-02\t224035.00\tINR
5000012347\t20240201\tIN03\tBenzin\t1800.000\tL\tVEND002\tCC-FLEET\t135000.00\tINR
5000012348\t20240205\tIN01\tDiesel Kraftstoff\t5100.000\tL\tVEND001\tCC-OPS-01\t357000.00\tINR
5000012349\t20240210\tDE01\tDieselkraftstoff\t2800.000\tL\tVEND003\tCC-DE-OPS\t392000.00\tEUR
5000012350\t20240215\tIN02\tNatural Gas\t12000.000\tKG\tVEND004\tCC-PLANT\t960000.00\tINR
5000012351\t20240220\tIN01\tDiesel Kraftstoff\t150000.000\tL\tVEND001\tCC-OPS-01\t10500000.00\tINR
5000012352\t20240301\tIN03\tBenzin\t2100.000\tL\tVEND002\tCC-FLEET\t157500.00\tINR
5000012353\t20240310\tUS01\tGasoline\t3200.000\tGAL\tVEND005\tCC-US\t9600.00\tUSD
5000012354\t20240315\tIN01\tDiesel Kraftstoff\t4800.000\tL\tVEND001\tCC-OPS-01\t336000.00\tINR
"""

UTILITY_SAMPLE = """Account Number,Meter Number,Billing Period From,Billing Period To,Reading Date,Units Consumed,Unit,Amount,Currency,Location,Tariff Code
KEB-10023441,MTR-BLR-001,01/01/2024,31/01/2024,03/02/2024,48500,kWh,338690,INR,Koramangala Office - Block A,HT-2
KEB-10023441,MTR-BLR-002,01/01/2024,31/01/2024,03/02/2024,32100,kWh,224370,INR,Koramangala Office - Block B,HT-2
KEB-10023442,MTR-BLR-003,15/01/2024,14/02/2024,16/02/2024,18700,kWh,130690,INR,Whitefield Data Centre,HT-1
MSEDCL-99112,MTR-MUM-001,01/01/2024,31/01/2024,05/02/2024,71200,kWh,427200,INR,Mumbai HQ,HT-2
MSEDCL-99112,MTR-MUM-002,01/01/2024,31/01/2024,05/02/2024,28400,kVAh,170400,INR,Mumbai Warehouse,LT-COM
KEB-10023443,MTR-BLR-004,01/02/2024,29/02/2024,04/03/2024,51200,kWh,358400,INR,Koramangala Office - Block A,HT-2
KEB-10023444,MTR-BLR-005,01/02/2024,29/02/2024,04/03/2024,620000,kWh,4340000,INR,Manufacturing Plant,HT-1
MSEDCL-99113,MTR-MUM-003,01/02/2024,29/02/2024,06/03/2024,43100,MWh,25860000,INR,Mumbai Processing Unit,EHT
"""

TRAVEL_SAMPLE = {
    "trips": [
        {
            "id": "TRIP-2024-001",
            "traveller": "Priya Sharma",
            "department": "Engineering",
            "cost_centre": "CC-TECH",
            "segments": [
                {
                    "type": "flight",
                    "origin": "BLR",
                    "destination": "DEL",
                    "departure_date": "2024-01-15",
                    "cabin": "economy",
                    "passengers": 1
                },
                {
                    "type": "hotel",
                    "hotel_name": "Taj Palace Delhi",
                    "city": "New Delhi",
                    "check_in": "2024-01-15",
                    "nights": 2
                },
                {
                    "type": "car",
                    "date": "2024-01-15",
                    "distance_km": 45
                },
                {
                    "type": "flight",
                    "origin": "DEL",
                    "destination": "BLR",
                    "departure_date": "2024-01-17",
                    "cabin": "economy",
                    "passengers": 1
                }
            ]
        },
        {
            "id": "TRIP-2024-002",
            "traveller": "Rahul Menon",
            "department": "Business Development",
            "cost_centre": "CC-BD",
            "segments": [
                {
                    "type": "flight",
                    "origin": "BLR",
                    "destination": "LHR",
                    "departure_date": "2024-02-10",
                    "cabin": "business",
                    "passengers": 1
                },
                {
                    "type": "hotel",
                    "hotel_name": "The Langham London",
                    "city": "London",
                    "check_in": "2024-02-10",
                    "nights": 4
                },
                {
                    "type": "flight",
                    "origin": "LHR",
                    "destination": "CDG",
                    "departure_date": "2024-02-14",
                    "cabin": "business",
                    "passengers": 1
                },
                {
                    "type": "hotel",
                    "hotel_name": "Hotel Le Marais",
                    "city": "Paris",
                    "check_in": "2024-02-14",
                    "nights": 2
                },
                {
                    "type": "flight",
                    "origin": "CDG",
                    "destination": "BLR",
                    "departure_date": "2024-02-16",
                    "cabin": "business",
                    "passengers": 1
                }
            ]
        },
        {
            "id": "TRIP-2024-003",
            "traveller": "Ananya Krishnan",
            "department": "Finance",
            "cost_centre": "CC-FIN",
            "segments": [
                {
                    "type": "flight",
                    "origin": "BOM",
                    "destination": "BLR",
                    "departure_date": "2024-03-05",
                    "cabin": "economy",
                    "passengers": 1
                },
                {
                    "type": "car",
                    "date": "2024-03-05",
                    "distance_km": 28
                },
                {
                    "type": "flight",
                    "origin": "BLR",
                    "destination": "BOM",
                    "departure_date": "2024-03-06",
                    "cabin": "economy",
                    "passengers": 1
                }
            ]
        }
    ]
}


class Command(BaseCommand):
    help = 'Seed the database with a demo organisation and sample emission data'

    def handle(self, *args, **options):
        self.stdout.write('Creating demo organisation...')

        org, _ = Organisation.objects.get_or_create(
            slug='acme-corp',
            defaults={'name': 'Acme Corporation'}
        )

        # Create analyst user
        analyst, created = User.objects.get_or_create(
            username='analyst',
            defaults={'email': 'analyst@acmecorp.com', 'first_name': 'Demo', 'last_name': 'Analyst'}
        )
        if created:
            analyst.set_password('breathe2024')
            analyst.save()

        OrganisationMembership.objects.get_or_create(
            user=analyst, organisation=org,
            defaults={'role': 'analyst'}
        )

        # Create admin user
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'admin@acmecorp.com', 'is_staff': True, 'is_superuser': True}
        )
        if created:
            admin.set_password('breathe2024')
            admin.save()

        OrganisationMembership.objects.get_or_create(
            user=admin, organisation=org,
            defaults={'role': 'admin'}
        )

        self.stdout.write('Ingesting SAP sample data...')
        sap_batch = IngestionBatch.objects.create(
            organisation=org, source_type='sap_flat_file',
            uploaded_by=admin, original_filename='SAP_MM_fuel_Q1_2024.txt',
            status='processing'
        )
        records_data, errors = parse_sap_file(SAP_SAMPLE.encode('utf-8'), sap_batch)
        with transaction.atomic():
            objs = [EmissionRecord(batch=sap_batch, organisation=org,
                                   **{k: v for k, v in rd.items() if k not in ('batch', 'organisation')})
                    for rd in records_data]
            EmissionRecord.objects.bulk_create(objs)
        sap_batch.status = 'completed'
        sap_batch.row_count_raw = len(records_data) + len(errors)
        sap_batch.row_count_accepted = len(records_data)
        sap_batch.row_count_rejected = len(errors)
        sap_batch.error_log = json.dumps(errors, default=str)
        sap_batch.save()
        self.stdout.write(f'  SAP: {len(records_data)} records, {len(errors)} errors')

        self.stdout.write('Ingesting Utility sample data...')
        util_batch = IngestionBatch.objects.create(
            organisation=org, source_type='utility_csv',
            uploaded_by=admin, original_filename='BESCOM_MSEDCL_electricity_Q1_2024.csv',
            status='processing'
        )
        records_data, errors = parse_utility_file(UTILITY_SAMPLE.encode('utf-8'), util_batch)
        with transaction.atomic():
            objs = [EmissionRecord(batch=util_batch, organisation=org,
                                   **{k: v for k, v in rd.items() if k not in ('batch', 'organisation')})
                    for rd in records_data]
            EmissionRecord.objects.bulk_create(objs)
        util_batch.status = 'completed'
        util_batch.row_count_raw = len(records_data) + len(errors)
        util_batch.row_count_accepted = len(records_data)
        util_batch.row_count_rejected = len(errors)
        util_batch.error_log = json.dumps(errors, default=str)
        util_batch.save()
        self.stdout.write(f'  Utility: {len(records_data)} records, {len(errors)} errors')

        self.stdout.write('Ingesting Travel sample data...')
        travel_batch = IngestionBatch.objects.create(
            organisation=org, source_type='travel_api',
            uploaded_by=admin, original_filename='navan_trips_Q1_2024.json',
            status='processing'
        )
        records_data, errors = parse_travel_json(TRAVEL_SAMPLE, travel_batch)
        with transaction.atomic():
            objs = [EmissionRecord(batch=travel_batch, organisation=org,
                                   **{k: v for k, v in rd.items() if k not in ('batch', 'organisation')})
                    for rd in records_data]
            EmissionRecord.objects.bulk_create(objs)
        travel_batch.status = 'completed'
        travel_batch.row_count_raw = len(records_data) + len(errors)
        travel_batch.row_count_accepted = len(records_data)
        travel_batch.row_count_rejected = len(errors)
        travel_batch.error_log = json.dumps(errors, default=str)
        travel_batch.save()
        self.stdout.write(f'  Travel: {len(records_data)} records, {len(errors)} errors')

        self.stdout.write(self.style.SUCCESS('\nDemo data seeded successfully!'))
        self.stdout.write('Login credentials:')
        self.stdout.write('  analyst / breathe2024')
        self.stdout.write('  admin   / breathe2024')
