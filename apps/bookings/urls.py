from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.bookings.views import AvailabilityView, BookingViewSet

router = DefaultRouter()
router.register('bookings', BookingViewSet, basename='booking')

urlpatterns = [
    path('availability/', AvailabilityView.as_view(), name='availability_search'),
    path('', include(router.urls)),
]
