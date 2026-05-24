from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.accounts.urls')),
    path('api/ingestion/', include('apps.ingestion.urls')),
    path('api/emissions/', include('apps.emissions.urls')),
    path('api/audit/', include('apps.audit.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
