from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmissionRecordViewSet, DashboardSummaryView, IngestionBatchViewSet, OrganisationViewSet

router = DefaultRouter()
router.register(r'records', EmissionRecordViewSet, basename='emission-record')
router.register(r'batches', IngestionBatchViewSet, basename='ingestion-batch')
router.register(r'organisations', OrganisationViewSet, basename='organisation')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', DashboardSummaryView.as_view(), name='dashboard-summary'),
]
