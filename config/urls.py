"""
config/urls.py (V2)
─────────────────────────────────────────────────────────────────────
URLs racine du projet.
Ajout : /api/ pour l'API REST + /api/schema/ pour la doc OpenAPI
─────────────────────────────────────────────────────────────────────
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    # Admin Django
    path('admin/', admin.site.urls),

    # Authentification
    path('', include('apps.accounts.urls')),

    # Applications métier
    path('dashboard/', include('apps.administration.urls')),
    path('pedagogie/', include('apps.pedagogie.urls')),
    path('examens/', include('apps.examens.urls')),
    path('stages/', include('apps.stages.urls')),
    path('ai/', include('apps.ai_agent.urls')),

    # API REST
    path('api/', include('apps.administration.api.urls')),

    # Documentation API (OpenAPI / Swagger)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/',
         SpectacularSwaggerView.as_view(url_name='schema'),
         name='swagger-ui'),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Debug Toolbar en développement
if settings.DEBUG:
    try:
        import debug_toolbar
        urlpatterns = [
            path('__debug__/', include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass
