from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Sum, Count, Q
from django.utils import timezone
from .models import EmissionRecord, EmissionRecordEditLog, Organisation, IngestionBatch
from .serializers import (
    EmissionRecordSerializer, EmissionRecordReviewSerializer,
    DashboardSummarySerializer, IngestionBatchSerializer, OrganisationSerializer
)


def get_user_org(request):
    membership = request.user.memberships.select_related('organisation').first()
    if not membership:
        return None
    return membership.organisation


class OrganisationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrganisationSerializer

    def get_queryset(self):
        return Organisation.objects.filter(memberships__user=self.request.user)


class IngestionBatchViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = IngestionBatchSerializer

    def get_queryset(self):
        org = get_user_org(self.request)
        if not org:
            return IngestionBatch.objects.none()
        return IngestionBatch.objects.filter(organisation=org)


class EmissionRecordViewSet(viewsets.ModelViewSet):
    serializer_class = EmissionRecordSerializer
    http_method_names = ['get', 'patch', 'head', 'options']  # No creating records by hand

    def get_queryset(self):
        org = get_user_org(self.request)
        if not org:
            return EmissionRecord.objects.none()
        qs = EmissionRecord.objects.filter(organisation=org).select_related(
            'batch', 'reviewed_by', 'locked_by'
        ).prefetch_related('edit_log__edited_by')

        # Filters
        scope = self.request.query_params.get('scope')
        category = self.request.query_params.get('category')
        review_status = self.request.query_params.get('review_status')
        is_flagged = self.request.query_params.get('is_flagged')
        batch_id = self.request.query_params.get('batch')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if scope:
            qs = qs.filter(scope=scope)
        if category:
            qs = qs.filter(category=category)
        if review_status:
            qs = qs.filter(review_status=review_status)
        if is_flagged is not None:
            qs = qs.filter(is_flagged=is_flagged.lower() == 'true')
        if batch_id:
            qs = qs.filter(batch_id=batch_id)
        if date_from:
            qs = qs.filter(activity_date__gte=date_from)
        if date_to:
            qs = qs.filter(activity_date__lte=date_to)

        return qs

    def partial_update(self, request, *args, **kwargs):
        record = self.get_object()
        if record.is_locked:
            return Response({'error': 'Record is locked for audit. No edits allowed.'}, status=403)

        # Log each changed field before saving
        allowed_editable = ['activity_quantity', 'activity_unit', 'emission_factor',
                            'emission_factor_source', 'activity_description', 'review_note']
        for field in allowed_editable:
            if field in request.data:
                old_val = str(getattr(record, field))
                new_val = str(request.data[field])
                if old_val != new_val:
                    EmissionRecordEditLog.objects.create(
                        record=record,
                        edited_by=request.user,
                        field_name=field,
                        old_value=old_val,
                        new_value=new_val,
                        reason=request.data.get('edit_reason', ''),
                    )

        serializer = self.get_serializer(record, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        record = self.get_object()
        if record.is_locked:
            return Response({'error': 'Record is locked.'}, status=403)

        ser = EmissionRecordReviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        action_val = ser.validated_data['action']

        status_map = {'approve': 'approved', 'reject': 'rejected', 'flag': 'flagged'}
        record.review_status = status_map[action_val]
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.review_note = ser.validated_data.get('review_note', '')

        if action_val == 'flag':
            record.is_flagged = True
            record.flag_reason = ser.validated_data.get('reason', '')

        record.save()
        return Response(EmissionRecordSerializer(record).data)

    @action(detail=True, methods=['post'])
    def lock(self, request, pk=None):
        record = self.get_object()
        if record.review_status != 'approved':
            return Response({'error': 'Only approved records can be locked.'}, status=400)
        record.is_locked = True
        record.locked_at = timezone.now()
        record.locked_by = request.user
        record.save()
        return Response({'status': 'locked'})

    @action(detail=False, methods=['post'])
    def bulk_approve(self, request):
        org = get_user_org(request)
        ids = request.data.get('ids', [])
        records = EmissionRecord.objects.filter(
            organisation=org, id__in=ids, is_locked=False, review_status='pending'
        )
        now = timezone.now()
        updated = records.update(
            review_status='approved',
            reviewed_by=request.user,
            reviewed_at=now
        )
        return Response({'approved': updated})


class DashboardSummaryView(APIView):
    def get(self, request):
        org = get_user_org(request)
        if not org:
            return Response({'error': 'No organisation found.'}, status=400)

        qs = EmissionRecord.objects.filter(organisation=org)

        totals = qs.aggregate(
            total=Sum('co2e_kg'),
            s1=Sum('co2e_kg', filter=Q(scope=1)),
            s2=Sum('co2e_kg', filter=Q(scope=2)),
            s3=Sum('co2e_kg', filter=Q(scope=3)),
        )

        review_counts = qs.values('review_status').annotate(count=Count('id'))
        review_map = {r['review_status']: r['count'] for r in review_counts}

        by_category = list(
            qs.values('category', 'scope')
            .annotate(co2e_kg=Sum('co2e_kg'), count=Count('id'))
            .order_by('-co2e_kg')
        )

        return Response({
            'total_co2e_kg': totals['total'] or 0,
            'scope1_co2e_kg': totals['s1'] or 0,
            'scope2_co2e_kg': totals['s2'] or 0,
            'scope3_co2e_kg': totals['s3'] or 0,
            'pending_count': review_map.get('pending', 0),
            'approved_count': review_map.get('approved', 0),
            'flagged_count': review_map.get('flagged', 0),
            'rejected_count': review_map.get('rejected', 0),
            'total_records': qs.count(),
            'by_category': by_category,
        })
