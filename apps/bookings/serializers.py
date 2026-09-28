from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.accounts.serializers import UserSerializer
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services import BookingService
from apps.services.models import Provider, Service
from apps.services.serializers import ProviderSerializer, ServiceSerializer


class BookingDetailSerializer(serializers.ModelSerializer):
    customer = UserSerializer(read_only=True)
    provider = ProviderSerializer(read_only=True)
    service = ServiceSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id',
            'customer',
            'provider',
            'service',
            'start_time',
            'end_time',
            'status',
            'status_display',
            'total_price',
            'customer_notes',
            'cancellation_reason',
            'cancelled_at',
            'cancelled_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class BookingCreateSerializer(serializers.Serializer):
    service_id = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.filter(is_active=True),
        source='service'
    )
    provider_id = serializers.PrimaryKeyRelatedField(
        queryset=Provider.objects.filter(is_active=True),
        source='provider'
    )
    start_time = serializers.DateTimeField()
    customer_notes = serializers.CharField(required=False, allow_blank=True, default='')

    def create(self, validated_data):
        user = self.context['request'].user
        service = validated_data['service']
        provider = validated_data['provider']
        start_time = validated_data['start_time']
        notes = validated_data.get('customer_notes', '')

        try:
            booking = BookingService.create_booking(
                customer=user,
                service=service,
                provider=provider,
                start_time=start_time,
                customer_notes=notes,
            )
            return booking
        except DjangoValidationError as e:
            if hasattr(e, 'message'):
                raise serializers.ValidationError({"detail": e.message})
            elif hasattr(e, 'messages'):
                raise serializers.ValidationError({"detail": e.messages[0]})
            raise serializers.ValidationError({"detail": str(e)})


class BookingCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class AvailabilityQuerySerializer(serializers.Serializer):
    service_id = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.filter(is_active=True),
        source='service'
    )
    provider_id = serializers.PrimaryKeyRelatedField(
        queryset=Provider.objects.filter(is_active=True),
        source='provider',
        required=False,
        allow_null=True
    )
    date = serializers.DateField(required=True)
    slot_interval = serializers.IntegerField(required=False, default=30, min_value=5, max_value=240)


class AvailableSlotSerializer(serializers.Serializer):
    provider_id = serializers.IntegerField()
    provider_name = serializers.CharField()
    service_id = serializers.IntegerField()
    service_name = serializers.CharField()
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    start_time_utc = serializers.DateTimeField()
    end_time_utc = serializers.DateTimeField()
