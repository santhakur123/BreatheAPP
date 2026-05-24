import json
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction
from apps.emissions.models import IngestionBatch, EmissionRecord, Organisation
from apps.ingestion.parsers.sap_parser import parse_sap_file
from apps.ingestion.parsers.utility_parser import parse_utility_file
from apps.ingestion.parsers.travel_parser import parse_travel_json


def get_user_org(request):
    membership = request.user.memberships.select_related('organisation').first()
    return membership.organisation if membership else None


class SAPIngestionView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        org = get_user_org(request)
        if not org:
            return Response({'error': 'No organisation'}, status=400)

        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'error': 'No file uploaded'}, status=400)

        batch = IngestionBatch.objects.create(
            organisation=org,
            source_type='sap_flat_file',
            uploaded_by=request.user,
            original_filename=uploaded_file.name,
            raw_file=uploaded_file,
            status='processing',
        )

        try:
            content = uploaded_file.read()
            records_data, errors = parse_sap_file(content, batch)

            with transaction.atomic():
                created = []
                for rd in records_data:
                    rd_copy = {k: v for k, v in rd.items() if k not in ('batch', 'organisation')}
                    obj = EmissionRecord(batch=batch, organisation=org, **rd_copy)
                    created.append(obj)
                EmissionRecord.objects.bulk_create(created)

            batch.status = 'completed'
            batch.row_count_raw = len(records_data) + len(errors)
            batch.row_count_accepted = len(records_data)
            batch.row_count_rejected = len(errors)
            batch.error_log = json.dumps(errors, default=str)
            batch.save()

            return Response({
                'batch_id': str(batch.id),
                'accepted': len(records_data),
                'rejected': len(errors),
                'errors': errors[:20],
            })

        except Exception as e:
            batch.status = 'failed'
            batch.error_log = str(e)
            batch.save()
            return Response({'error': str(e)}, status=500)


class UtilityIngestionView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        org = get_user_org(request)
        if not org:
            return Response({'error': 'No organisation'}, status=400)

        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'error': 'No file uploaded'}, status=400)

        batch = IngestionBatch.objects.create(
            organisation=org,
            source_type='utility_csv',
            uploaded_by=request.user,
            original_filename=uploaded_file.name,
            raw_file=uploaded_file,
            status='processing',
        )

        try:
            content = uploaded_file.read()
            records_data, errors = parse_utility_file(content, batch)

            with transaction.atomic():
                created = []
                for rd in records_data:
                    rd_copy = {k: v for k, v in rd.items() if k not in ('batch', 'organisation')}
                    obj = EmissionRecord(batch=batch, organisation=org, **rd_copy)
                    created.append(obj)
                EmissionRecord.objects.bulk_create(created)

            batch.status = 'completed'
            batch.row_count_raw = len(records_data) + len(errors)
            batch.row_count_accepted = len(records_data)
            batch.row_count_rejected = len(errors)
            batch.error_log = json.dumps(errors, default=str)
            batch.save()

            return Response({
                'batch_id': str(batch.id),
                'accepted': len(records_data),
                'rejected': len(errors),
                'errors': errors[:20],
            })

        except Exception as e:
            batch.status = 'failed'
            batch.error_log = str(e)
            batch.save()
            return Response({'error': str(e)}, status=500)


class TravelIngestionView(APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def post(self, request):
        org = get_user_org(request)
        if not org:
            return Response({'error': 'No organisation'}, status=400)

        # Accept either file upload or direct JSON body
        if 'file' in request.FILES:
            uploaded_file = request.FILES['file']
            filename = uploaded_file.name
            try:
                data = json.loads(uploaded_file.read().decode('utf-8'))
            except json.JSONDecodeError as e:
                return Response({'error': f'Invalid JSON: {e}'}, status=400)
        else:
            data = request.data
            filename = 'direct_json_upload'

        batch = IngestionBatch.objects.create(
            organisation=org,
            source_type='travel_api',
            uploaded_by=request.user,
            original_filename=filename,
            status='processing',
        )

        try:
            records_data, errors = parse_travel_json(data, batch)

            with transaction.atomic():
                created = []
                for rd in records_data:
                    rd_copy = {k: v for k, v in rd.items() if k not in ('batch', 'organisation')}
                    obj = EmissionRecord(batch=batch, organisation=org, **rd_copy)
                    created.append(obj)
                EmissionRecord.objects.bulk_create(created)

            batch.status = 'completed'
            batch.row_count_raw = len(records_data) + len(errors)
            batch.row_count_accepted = len(records_data)
            batch.row_count_rejected = len(errors)
            batch.error_log = json.dumps(errors, default=str)
            batch.save()

            return Response({
                'batch_id': str(batch.id),
                'accepted': len(records_data),
                'rejected': len(errors),
                'errors': errors[:20],
            })

        except Exception as e:
            batch.status = 'failed'
            batch.error_log = str(e)
            batch.save()
            return Response({'error': str(e)}, status=500)
