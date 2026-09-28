from django.contrib import admin

from apps.bookings.models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'provider', 'service', 'start_time', 'end_time', 'status', 'total_price', 'created_at')
    list_filter = ('status', 'service', 'provider', 'start_time')
    search_fields = ('customer__email', 'customer__username', 'provider__name', 'service__name')
    readonly_fields = ('created_at', 'updated_at', 'cancelled_at', 'cancelled_by')
