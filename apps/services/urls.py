from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.services.views import (
    ProviderViewSet,
    ServiceViewSet,
    TimeOffViewSet,
    WorkingHourViewSet,
)

router = DefaultRouter()
router.register('services', ServiceViewSet, basename='service')
router.register('providers', ProviderViewSet, basename='provider')
router.register('working-hours', WorkingHourViewSet, basename='working-hour')
router.register('time-offs', TimeOffViewSet, basename='time-off')

urlpatterns = [
    path('', include(router.urls)),
]
