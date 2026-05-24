from rest_framework import serializers
from .models import EmissionRecord, EmissionRecordEditLog, Organisation, IngestionBatch
from django.contrib.auth.models import User


class OrganisationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organisation
        fields = ['id', 'name', 'slug', 'created_at']


class IngestionBatchSerializer(serializers.ModelSerializer):
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)

    class Meta:
        model = IngestionBatch
        fields = [
            'id', 'source_type', 'uploaded_by_username', 'uploaded_at',
            'original_filename', 'status', 'row_count_raw',
            'row_count_accepted', 'row_count_rejected', 'error_log', 'metadata'
        ]


class EmissionRecordEditLogSerializer(serializers.ModelSerializer):
    edited_by_username = serializers.CharField(source='edited_by.username', read_only=True)

    class Meta:
        model = EmissionRecordEditLog
        fields = ['id', 'edited_by_username', 'edited_at', 'field_name', 'old_value', 'new_value', 'reason']


class EmissionRecordSerializer(serializers.ModelSerializer):
    reviewed_by_username = serializers.CharField(source='reviewed_by.username', read_only=True)
    batch_source_type = serializers.CharField(source='batch.source_type', read_only=True)
    edit_log = EmissionRecordEditLogSerializer(many=True, read_only=True)

    class Meta:
        model = EmissionRecord
        fields = [
            'id', 'scope', 'category', 'activity_date', 'activity_quantity',
            'activity_unit', 'activity_description', 'emission_factor',
            'emission_factor_source', 'co2e_kg', 'source_system', 'source_row_id',
            'raw_data', 'unit_conversion_applied', 'unit_conversion_note',
            'date_parse_note', 'review_status', 'reviewed_by_username',
            'reviewed_at', 'review_note', 'is_flagged', 'flag_reason',
            'is_locked', 'locked_at', 'batch', 'batch_source_type',
            'created_at', 'updated_at', 'edit_log',
        ]
        read_only_fields = ['co2e_kg', 'created_at', 'updated_at', 'is_locked', 'locked_at']


class EmissionRecordReviewSerializer(serializers.Serializer):
    """Used for the review/approve/reject action endpoint."""
    action = serializers.ChoiceField(choices=['approve', 'reject', 'flag'])
    review_note = serializers.CharField(required=False, allow_blank=True)
    reason = serializers.CharField(required=False, allow_blank=True)


class DashboardSummarySerializer(serializers.Serializer):
    total_co2e_kg = serializers.DecimalField(max_digits=18, decimal_places=2)
    scope1_co2e_kg = serializers.DecimalField(max_digits=18, decimal_places=2)
    scope2_co2e_kg = serializers.DecimalField(max_digits=18, decimal_places=2)
    scope3_co2e_kg = serializers.DecimalField(max_digits=18, decimal_places=2)
    pending_count = serializers.IntegerField()
    approved_count = serializers.IntegerField()
    flagged_count = serializers.IntegerField()
    rejected_count = serializers.IntegerField()
    total_records = serializers.IntegerField()
    by_category = serializers.ListField()
