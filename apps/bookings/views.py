from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsBookingParticipantOrAdmin
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.serializers import (
    AvailabilityQuerySerializer,
    AvailableSlotSerializer,
    BookingCancelSerializer,
    BookingCreateSerializer,
    BookingDetailSerializer,
)
from apps.bookings.services import AvailabilityService, BookingService
from apps.services.models import Provider


class AvailabilityView(APIView):
    """
    Search available time slots for a service and date.
    Can be filtered to a specific provider or returns slots for all available providers.
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='service_id', description='ID of the service', required=True, type=int),
            OpenApiParameter(name='date', description='Date in YYYY-MM-DD format', required=True, type=str),
            OpenApiParameter(name='provider_id', description='Optional provider ID filter', required=False, type=int),
            OpenApiParameter(name='slot_interval', description='Slot step in minutes (default 30)', required=False, type=int),
        ],
        responses={200: AvailableSlotSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        serializer = AvailabilityQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        service = serializer.validated_data['service']
        provider = serializer.validated_data.get('provider')
        target_date = serializer.validated_data['date']
        slot_interval = serializer.validated_data.get('slot_interval', 30)

        all_slots = []
        if provider:
            providers = [provider]
        else:
            providers = Provider.objects.filter(services=service, is_active=True)

        for p in providers:
            slots = AvailabilityService.get_available_slots(
                service=service,
                provider=p,
                target_date=target_date,
                slot_interval_minutes=slot_interval
            )
            all_slots.extend(slots)

        # Sort slots by start_time
        all_slots.sort(key=lambda x: x['start_time'])

        return Response(all_slots, status=status.HTTP_200_OK)


class BookingViewSet(viewsets.ModelViewSet):
    """
    Manage bookings.
    - Customers can view their own bookings and create new bookings.
    - Providers can view and manage bookings assigned to them.
    - Admins can view and manage all bookings.
    """
    permission_classes = [permissions.IsAuthenticated, IsBookingParticipantOrAdmin]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'create':
            return BookingCreateSerializer
        if self.action == 'cancel':
            return BookingCancelSerializer
        return BookingDetailSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Booking.objects.select_related('customer', 'provider', 'service').all()

        if not user.is_authenticated:
            return queryset.none()

        is_detail = getattr(self, 'detail', False) or self.action in [
            'retrieve', 'update', 'partial_update', 'destroy', 'cancel', 'confirm', 'complete'
        ]

        if user.is_business_admin:
            my_bookings = self.request.query_params.get('my_bookings', '').lower() in ['true', '1']
            as_customer = self.request.query_params.get('as_customer', '').lower() in ['true', '1']
            if my_bookings or as_customer:
                queryset = queryset.filter(customer=user)
        elif user.is_provider:
            if is_detail:
                queryset = queryset.filter(Q(customer=user) | Q(provider__user=user))
            else:
                as_provider = self.request.query_params.get('as_provider', '').lower() in ['true', '1']
                as_customer = self.request.query_params.get('as_customer', '').lower() in ['true', '1']
                role_param = self.request.query_params.get('role', '').lower()

                if as_customer:
                    queryset = queryset.filter(customer=user)
                elif as_provider or role_param == 'provider' or self.request.query_params.get('assigned', '').lower() in ['true', '1']:
                    queryset = queryset.filter(provider__user=user)
                elif self.request.query_params.get('all', '').lower() in ['true', '1']:
                    queryset = queryset.filter(Q(customer=user) | Q(provider__user=user))
                else:
                    # Providers manage the appointments assigned to their provider profile by default.
                    queryset = queryset.filter(provider__user=user)
        else:
            # Customer sees only their own bookings
            queryset = queryset.filter(customer=user)

        # Filtering
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param.upper())

        provider_id = self.request.query_params.get('provider_id')
        if provider_id:
            queryset = queryset.filter(provider_id=provider_id)

        service_id = self.request.query_params.get('service_id')
        if service_id:
            queryset = queryset.filter(service_id=service_id)

        start_date = self.request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(start_time__date__gte=start_date)

        end_date = self.request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(start_time__date__lte=end_date)

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        detail_serializer = BookingDetailSerializer(booking)
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        serializer = BookingCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get('reason', '')

        try:
            cancelled_booking = BookingService.cancel_booking(booking, request.user, reason)
            return Response(BookingDetailSerializer(cancelled_booking).data, status=status.HTTP_200_OK)
        except DjangoValidationError as e:
            return Response({"detail": str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        booking = self.get_object()
        user = request.user
        if not (user.is_business_admin or (booking.provider.user_id and booking.provider.user_id == user.id)):
            return Response({"detail": "Only the provider or business admin can confirm bookings."}, status=status.HTTP_403_FORBIDDEN)

        try:
            confirmed_booking = BookingService.confirm_booking(booking, user)
            return Response(BookingDetailSerializer(confirmed_booking).data, status=status.HTTP_200_OK)
        except DjangoValidationError as e:
            return Response({"detail": str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        booking = self.get_object()
        user = request.user
        if not (user.is_business_admin or (booking.provider.user_id and booking.provider.user_id == user.id)):
            return Response({"detail": "Only the provider or business admin can complete bookings."}, status=status.HTTP_403_FORBIDDEN)

        try:
            completed_booking = BookingService.complete_booking(booking, user)
            return Response(BookingDetailSerializer(completed_booking).data, status=status.HTTP_200_OK)
        except DjangoValidationError as e:
            return Response({"detail": str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)
