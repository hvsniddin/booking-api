from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminUserOrReadOnly, IsBusinessAdmin
from apps.services.models import Provider, Service, TimeOff, WorkingHour
from apps.services.serializers import (
    ProviderSerializer,
    ServiceSerializer,
    TimeOffSerializer,
    WorkingHourSerializer,
)


class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    permission_classes = [IsAdminUserOrReadOnly]

    def get_queryset(self):
        queryset = super().get_queryset()
        if not (self.request.user and self.request.user.is_authenticated and self.request.user.is_business_admin):
            # Only show active services to customers / public
            queryset = queryset.filter(is_active=True)
        return queryset


class ProviderViewSet(viewsets.ModelViewSet):
    queryset = Provider.objects.all().prefetch_related('services', 'working_hours')
    serializer_class = ProviderSerializer
    permission_classes = [IsAdminUserOrReadOnly]

    def get_queryset(self):
        queryset = super().get_queryset()
        service_id = self.request.query_params.get('service_id')
        if service_id:
            queryset = queryset.filter(services__id=service_id)
        if not (self.request.user and self.request.user.is_authenticated and self.request.user.is_business_admin):
            queryset = queryset.filter(is_active=True)
        return queryset.distinct()


class WorkingHourViewSet(viewsets.ModelViewSet):
    queryset = WorkingHour.objects.all().select_related('provider')
    serializer_class = WorkingHourSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        provider_id = self.request.query_params.get('provider_id')
        if provider_id:
            queryset = queryset.filter(provider_id=provider_id)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        provider = serializer.validated_data.get('provider')
        if not user.is_business_admin and (not provider.user or provider.user != user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You can only manage working hours for your own provider profile.")
        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        provider = serializer.instance.provider
        if not user.is_business_admin and (not provider.user or provider.user != user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You can only manage working hours for your own provider profile.")
        serializer.save()


class TimeOffViewSet(viewsets.ModelViewSet):
    queryset = TimeOff.objects.all().select_related('provider')
    serializer_class = TimeOffSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        provider_id = self.request.query_params.get('provider_id')
        if provider_id:
            queryset = queryset.filter(provider_id=provider_id)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        provider = serializer.validated_data.get('provider')
        if not user.is_business_admin and (not provider.user or provider.user != user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You can only manage time-offs for your own provider profile.")
        serializer.save()
