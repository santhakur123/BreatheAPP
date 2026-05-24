from django.db import models
from django.contrib.auth.models import User
import uuid


class Organisation(models.Model):
    """
    Top-level tenant. Every row of data belongs to one org.
    Multi-tenancy is enforced at the queryset level via OrganisationQuerySet.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class OrganisationMembership(models.Model):
    ROLES = [('admin', 'Admin'), ('analyst', 'Analyst'), ('viewer', 'Viewer')]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLES, default='analyst')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'organisation')


class IngestionBatch(models.Model):
    """
    One upload event. Tracks provenance: who uploaded what, when, from which source system.
    A batch may produce many EmissionRecord rows.
    """
    SOURCE_TYPES = [
        ('sap_flat_file', 'SAP Flat File (IDoc/XLSX export)'),
        ('utility_csv', 'Utility Portal CSV Export'),
        ('travel_api', 'Corporate Travel Platform (Navan/Concur JSON)'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name='batches')
    source_type = models.CharField(max_length=50, choices=SOURCE_TYPES)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    original_filename = models.CharField(max_length=500, blank=True)
    raw_file = models.FileField(upload_to='raw_uploads/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    row_count_raw = models.IntegerField(default=0)
    row_count_accepted = models.IntegerField(default=0)
    row_count_rejected = models.IntegerField(default=0)
    error_log = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # source-specific metadata

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.organisation} / {self.source_type} / {self.uploaded_at:%Y-%m-%d}"


class EmissionRecord(models.Model):
    """
    The canonical normalised emission row. One row = one activity event.
    Every field that can vary by source is tracked alongside its original raw value.

    Scope classification follows GHG Protocol:
      Scope 1 = direct combustion (fuel)
      Scope 2 = purchased electricity
      Scope 3 = everything else (travel, supply chain, etc.)
    """
    SCOPE_CHOICES = [(1, 'Scope 1'), (2, 'Scope 2'), (3, 'Scope 3')]

    CATEGORY_CHOICES = [
        # Scope 1
        ('fuel_diesel', 'Diesel Combustion'),
        ('fuel_petrol', 'Petrol Combustion'),
        ('fuel_natural_gas', 'Natural Gas Combustion'),
        # Scope 2
        ('electricity', 'Purchased Electricity'),
        # Scope 3
        ('flight_domestic', 'Flight – Domestic'),
        ('flight_short_haul', 'Flight – Short Haul'),
        ('flight_long_haul', 'Flight – Long Haul'),
        ('hotel_stay', 'Hotel Stay'),
        ('ground_transport', 'Ground Transport (Car/Rail)'),
        ('procurement', 'Procurement / Supply Chain'),
    ]

    REVIEW_STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('flagged', 'Flagged – Needs Clarification'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name='emission_records')
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name='records')

    # --- Classification ---
    scope = models.IntegerField(choices=SCOPE_CHOICES)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)

    # --- Activity data (normalised) ---
    activity_date = models.DateField()                         # normalised to ISO date
    activity_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    activity_unit = models.CharField(max_length=50)            # always SI or named unit (litre, kWh, km, nights)
    activity_description = models.TextField(blank=True)

    # --- Emission calculation ---
    emission_factor = models.DecimalField(max_digits=18, decimal_places=8)
    emission_factor_source = models.CharField(max_length=255)  # e.g. "DEFRA 2023", "CEA India 2023"
    co2e_kg = models.DecimalField(max_digits=18, decimal_places=4)  # computed: quantity * factor

    # --- Source of truth tracking ---
    source_system = models.CharField(max_length=100)           # e.g. "SAP ECC 6.0", "BESCOM portal"
    source_row_id = models.CharField(max_length=255, blank=True)  # original row ID in source
    raw_data = models.JSONField(default=dict)                  # snapshot of original row, unmodified

    # --- Normalisation audit ---
    # Were units converted? Was date parsed from a non-ISO format? Track it.
    unit_conversion_applied = models.BooleanField(default=False)
    unit_conversion_note = models.TextField(blank=True)
    date_parse_note = models.TextField(blank=True)

    # --- Review workflow ---
    review_status = models.CharField(max_length=20, choices=REVIEW_STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_records'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    # --- Suspicious flag ---
    is_flagged = models.BooleanField(default=False)
    flag_reason = models.TextField(blank=True)

    # --- Locked for audit ---
    is_locked = models.BooleanField(default=False)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='locked_records'
    )

    # --- Timestamps ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-activity_date']
        indexes = [
            models.Index(fields=['organisation', 'scope', 'activity_date']),
            models.Index(fields=['organisation', 'review_status']),
            models.Index(fields=['batch']),
            models.Index(fields=['is_flagged']),
        ]

    def __str__(self):
        return f"{self.organisation} | {self.category} | {self.activity_date} | {self.co2e_kg} kg CO2e"

    def save(self, *args, **kwargs):
        # Recompute co2e whenever quantity or factor changes
        self.co2e_kg = self.activity_quantity * self.emission_factor
        super().save(*args, **kwargs)


class EmissionRecordEditLog(models.Model):
    """
    Immutable audit trail. Any edit to an EmissionRecord appends a row here.
    Never deleted. Gives auditors full edit history.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(EmissionRecord, on_delete=models.CASCADE, related_name='edit_log')
    edited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    edited_at = models.DateTimeField(auto_now_add=True)
    field_name = models.CharField(max_length=100)
    old_value = models.TextField()
    new_value = models.TextField()
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ['edited_at']
