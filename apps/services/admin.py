from django.contrib import admin

from apps.services.models import Provider, Service, TimeOff, WorkingHour


class WorkingHourInline(admin.TabularInline):
    model = WorkingHour
    extra = 7


class TimeOffInline(admin.TabularInline):
    model = TimeOff
    extra = 1


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'duration_minutes', 'price', 'buffer_time_minutes', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone_number', 'timezone', 'is_active')
    list_filter = ('is_active', 'timezone')
    search_fields = ('name', 'email', 'phone_number')
    filter_horizontal = ('services',)
    inlines = [WorkingHourInline, TimeOffInline]


@admin.register(WorkingHour)
class WorkingHourAdmin(admin.ModelAdmin):
    list_display = ('provider', 'day_of_week', 'start_time', 'end_time', 'is_day_off')
    list_filter = ('day_of_week', 'is_day_off', 'provider')


@admin.register(TimeOff)
class TimeOffAdmin(admin.ModelAdmin):
    list_display = ('provider', 'start_datetime', 'end_datetime', 'reason')
    list_filter = ('provider',)
    search_fields = ('reason', 'provider__name')
