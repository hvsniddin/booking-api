from datetime import date, datetime, time, timedelta
import zoneinfo
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking, BookingStatus
from apps.services.models import DayOfWeek, Provider, Service, TimeOff, WorkingHour


class AvailabilityService:
    """
    Computes available time slots for booking a service with a provider.
    """

    @classmethod
    def get_available_slots(cls, service: Service, provider: Provider, target_date: date, slot_interval_minutes: int = None):
        """
        Calculates all free time slots for a specific service and provider on a given date.
        """
        if not provider.is_active or not service.is_active:
            return []

        if not provider.services.filter(id=service.id).exists():
            return []

        # Find provider working hours for target date's weekday
        # Python weekday(): Monday is 0 and Sunday is 6
        weekday = target_date.weekday()
        working_hour = WorkingHour.objects.filter(
            provider=provider,
            day_of_week=weekday,
            is_day_off=False
        ).first()

        if not working_hour:
            return []

        duration_minutes = service.duration_minutes
        buffer_minutes = service.buffer_time_minutes
        step_minutes = slot_interval_minutes or 30  # default 30 min step or custom

        # Timezone handling
        tz_str = provider.timezone or settings.TIME_ZONE
        try:
            tz = zoneinfo.ZoneInfo(tz_str)
        except Exception:
            tz = zoneinfo.ZoneInfo('UTC')

        start_dt = datetime.combine(target_date, working_hour.start_time).replace(tzinfo=tz)
        end_dt = datetime.combine(target_date, working_hour.end_time).replace(tzinfo=tz)

        # Get existing bookings for this provider on this day (including buffer)
        day_start_utc = start_dt.astimezone(zoneinfo.ZoneInfo('UTC'))
        day_end_utc = end_dt.astimezone(zoneinfo.ZoneInfo('UTC'))

        existing_bookings = Booking.objects.filter(
            provider=provider,
            status__in=[BookingStatus.PENDING, BookingStatus.CONFIRMED],
            start_time__lt=day_end_utc,
            end_time__gt=day_start_utc
        )

        # Fetch time off records
        time_offs = TimeOff.objects.filter(
            provider=provider,
            start_datetime__lt=day_end_utc,
            end_datetime__gt=day_start_utc
        )

        now_in_tz = timezone.now().astimezone(tz)

        available_slots = []
        current_cursor = start_dt

        while current_cursor + timedelta(minutes=duration_minutes) <= end_dt:
            slot_start = current_cursor
            slot_end = current_cursor + timedelta(minutes=duration_minutes)
            slot_blocked_end = slot_end + timedelta(minutes=buffer_minutes)

            # Slot cannot be in the past
            if slot_start <= now_in_tz:
                current_cursor += timedelta(minutes=step_minutes)
                continue

            slot_start_utc = slot_start.astimezone(zoneinfo.ZoneInfo('UTC'))
            slot_end_utc = slot_end.astimezone(zoneinfo.ZoneInfo('UTC'))
            slot_blocked_end_utc = slot_blocked_end.astimezone(zoneinfo.ZoneInfo('UTC'))

            # Check overlap with existing bookings
            is_booked = False
            for b in existing_bookings:
                # Existing booking occupies [b.start_time, b.end_time + b.service.buffer_time_minutes]
                b_buffer = b.service.buffer_time_minutes if hasattr(b, 'service') and b.service else 0
                b_end_with_buffer = b.end_time + timedelta(minutes=b_buffer)
                if not (slot_blocked_end_utc <= b.start_time or slot_start_utc >= b_end_with_buffer):
                    is_booked = True
                    break

            if is_booked:
                current_cursor += timedelta(minutes=step_minutes)
                continue

            # Check overlap with time-offs
            is_time_off = False
            for to in time_offs:
                if not (slot_end_utc <= to.start_datetime or slot_start_utc >= to.end_datetime):
                    is_time_off = True
                    break

            if is_time_off:
                current_cursor += timedelta(minutes=step_minutes)
                continue

            available_slots.append({
                'provider_id': provider.id,
                'provider_name': provider.name,
                'service_id': service.id,
                'service_name': service.name,
                'start_time': slot_start.isoformat(),
                'end_time': slot_end.isoformat(),
                'start_time_utc': slot_start_utc.isoformat(),
                'end_time_utc': slot_end.astimezone(zoneinfo.ZoneInfo('UTC')).isoformat(),
            })

            current_cursor += timedelta(minutes=step_minutes)

        return available_slots


class BookingService:
    """
    Handles booking creation, status transitions, and cancellation with concurrency protection.
    """
    CANCELLATION_MIN_HOURS_AHEAD = 2

    @classmethod
    @transaction.atomic
    def create_booking(
        cls,
        customer,
        service: Service,
        provider: Provider,
        start_time: datetime,
        customer_notes: str = ''
    ) -> Booking:
        """
        Creates a booking with strict concurrency protection (select_for_update) to prevent double bookings.
        """
        # 1. Pessimistic lock on provider row to prevent concurrent race conditions
        locked_provider = Provider.objects.select_for_update().get(id=provider.id)

        if not locked_provider.is_active:
            raise ValidationError("This provider is currently inactive.")

        if not service.is_active:
            raise ValidationError("This service is currently inactive.")

        if not locked_provider.services.filter(id=service.id).exists():
            raise ValidationError(f"Provider '{locked_provider.name}' does not offer service '{service.name}'.")

        # 2. Timezone & time validation
        if timezone.is_naive(start_time):
            start_time = timezone.make_aware(start_time, timezone.utc)
        else:
            start_time = start_time.astimezone(timezone.utc)

        now = timezone.now()
        if start_time <= now:
            raise ValidationError("Cannot book appointments in the past.")

        end_time = start_time + timedelta(minutes=service.duration_minutes)

        # 3. Check provider working hours
        prov_tz_str = locked_provider.timezone or settings.TIME_ZONE
        try:
            prov_tz = zoneinfo.ZoneInfo(prov_tz_str)
        except Exception:
            prov_tz = zoneinfo.ZoneInfo('UTC')

        start_in_prov_tz = start_time.astimezone(prov_tz)
        end_in_prov_tz = end_time.astimezone(prov_tz)

        weekday = start_in_prov_tz.weekday()
        working_hour = WorkingHour.objects.filter(
            provider=locked_provider,
            day_of_week=weekday,
            is_day_off=False
        ).first()

        if not working_hour:
            raise ValidationError("Provider does not work on this day.")

        work_start_dt = datetime.combine(start_in_prov_tz.date(), working_hour.start_time).replace(tzinfo=prov_tz)
        work_end_dt = datetime.combine(start_in_prov_tz.date(), working_hour.end_time).replace(tzinfo=prov_tz)

        if start_in_prov_tz < work_start_dt or end_in_prov_tz > work_end_dt:
            raise ValidationError(
                f"Booking time is outside provider working hours ({working_hour.start_time.strftime('%H:%M')} - {working_hour.end_time.strftime('%H:%M')})."
            )

        # 4. Check time-offs
        if TimeOff.objects.filter(
            provider=locked_provider,
            start_datetime__lt=end_time,
            end_datetime__gt=start_time
        ).exists():
            raise ValidationError("Provider is on time-off during the requested time.")

        # 5. Check overlapping bookings (Double booking prevention)
        buffer_minutes = service.buffer_time_minutes
        blocked_end_time = end_time + timedelta(minutes=buffer_minutes)

        overlap_exists = Booking.objects.filter(
            provider=locked_provider,
            status__in=[BookingStatus.PENDING, BookingStatus.CONFIRMED],
            start_time__lt=blocked_end_time,
            end_time__gt=start_time
        ).exists()

        if overlap_exists:
            raise ValidationError("The requested time slot is no longer available. Please choose another time.")

        # 6. Create Booking
        booking = Booking.objects.create(
            customer=customer,
            provider=locked_provider,
            service=service,
            start_time=start_time,
            end_time=end_time,
            status=BookingStatus.PENDING,
            total_price=service.price,
            customer_notes=customer_notes,
        )

        return booking

    @classmethod
    def cancel_booking(cls, booking: Booking, user, reason: str = '') -> Booking:
        """
        Cancels a booking subject to policy restrictions.
        """
        if booking.status == BookingStatus.CANCELLED:
            raise ValidationError("Booking is already cancelled.")

        if booking.status == BookingStatus.COMPLETED:
            raise ValidationError("Cannot cancel a completed booking.")

        is_admin_or_provider = user.is_business_admin or (
            booking.provider.user_id and booking.provider.user_id == user.id
        )

        # Cancellation policy for customers: must cancel at least X hours ahead
        if not is_admin_or_provider:
            if booking.customer_id != user.id:
                raise ValidationError("You do not have permission to cancel this booking.")

            min_cancel_time = timezone.now() + timedelta(hours=cls.CANCELLATION_MIN_HOURS_AHEAD)
            if booking.start_time < min_cancel_time:
                raise ValidationError(
                    f"Cancellations must be made at least {cls.CANCELLATION_MIN_HOURS_AHEAD} hours prior to appointment."
                )

        booking.status = BookingStatus.CANCELLED
        booking.cancellation_reason = reason
        booking.cancelled_at = timezone.now()
        booking.cancelled_by = user
        booking.save()
        return booking

    @classmethod
    def confirm_booking(cls, booking: Booking, user) -> Booking:
        """
        Confirms a pending booking.
        """
        if booking.status != BookingStatus.PENDING:
            raise ValidationError(f"Cannot confirm booking with status '{booking.status}'.")

        booking.status = BookingStatus.CONFIRMED
        booking.save()
        return booking

    @classmethod
    def complete_booking(cls, booking: Booking, user) -> Booking:
        """
        Marks a confirmed booking as completed.
        """
        if booking.status != BookingStatus.CONFIRMED:
            raise ValidationError(f"Only confirmed bookings can be marked as completed.")

        booking.status = BookingStatus.COMPLETED
        booking.save()
        return booking
