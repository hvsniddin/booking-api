from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.services.models import DayOfWeek, Provider, Service, TimeOff, WorkingHour


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = [
            'id',
            'name',
            'description',
            'duration_minutes',
            'price',
            'buffer_time_minutes',
            'is_active',
            'created_at',
            'updated_at',
        ]


class WorkingHourSerializer(serializers.ModelSerializer):
    day_of_week_display = serializers.CharField(source='get_day_of_week_display', read_only=True)

    class Meta:
        model = WorkingHour
        fields = [
            'id',
            'provider',
            'day_of_week',
            'day_of_week_display',
            'start_time',
            'end_time',
            'is_day_off',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        is_day_off = attrs.get('is_day_off', getattr(self.instance, 'is_day_off', False))
        start_time = attrs.get('start_time', getattr(self.instance, 'start_time', None))
        end_time = attrs.get('end_time', getattr(self.instance, 'end_time', None))

        if not is_day_off and start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError({"end_time": "End time must be after start time."})
        return attrs


class TimeOffSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeOff
        fields = [
            'id',
            'provider',
            'start_datetime',
            'end_datetime',
            'reason',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        start_datetime = attrs.get('start_datetime', getattr(self.instance, 'start_datetime', None))
        end_datetime = attrs.get('end_datetime', getattr(self.instance, 'end_datetime', None))

        if start_datetime and end_datetime and start_datetime >= end_datetime:
            raise serializers.ValidationError({"end_datetime": "End datetime must be after start datetime."})
        return attrs


class ProviderSerializer(serializers.ModelSerializer):
    services = ServiceSerializer(many=True, read_only=True)
    service_ids = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.all(),
        many=True,
        write_only=True,
        required=False,
        source='services'
    )
    working_hours = WorkingHourSerializer(many=True, read_only=True)
    user_detail = UserSerializer(source='user', read_only=True)

    class Meta:
        model = Provider
        fields = [
            'id',
            'user',
            'user_detail',
            'name',
            'email',
            'phone_number',
            'bio',
            'services',
            'service_ids',
            'working_hours',
            'timezone',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        services = validated_data.pop('services', [])
        provider = Provider.objects.create(**validated_data)
        if services:
            provider.services.set(services)
        return provider

    def update(self, instance, validated_data):
        services = validated_data.pop('services', None)
        provider = super().update(instance, validated_data)
        if services is not None:
            provider.services.set(services)
        return provider
