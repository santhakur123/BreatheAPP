from django.urls import path
from .views import SAPIngestionView, UtilityIngestionView, TravelIngestionView

urlpatterns = [
    path('sap/', SAPIngestionView.as_view(), name='ingest-sap'),
    path('utility/', UtilityIngestionView.as_view(), name='ingest-utility'),
    path('travel/', TravelIngestionView.as_view(), name='ingest-travel'),
]
