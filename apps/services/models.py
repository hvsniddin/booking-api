from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class Service(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(
        validators=[MinValueValidator(5)],
        help_text="Duration in minutes (e.g. 30, 45, 60)"
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    buffer_time_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Buffer/cleanup time needed after service in minutes"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.duration_minutes} mins) - ${self.price}"


class Provider(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='provider_profile',
        null=True,
        blank=True
    )
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    bio = models.TextField(blank=True)
    services = models.ManyToManyField(
        Service,
        related_name='providers',
        blank=True
    )
    timezone = models.CharField(max_length=64, default='UTC')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def clean(self):
        if self.user and not self.email:
            self.email = self.user.email
        if self.user and not self.name:
            self.name = self.user.get_full_name() or self.user.username


class DayOfWeek(models.IntegerChoices):
    MONDAY = 0, 'Monday'
    TUESDAY = 1, 'Tuesday'
    WEDNESDAY = 2, 'Wednesday'
    THURSDAY = 3, 'Thursday'
    FRIDAY = 4, 'Friday'
    SATURDAY = 5, 'Saturday'
    SUNDAY = 6, 'Sunday'


class WorkingHour(models.Model):
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='working_hours'
    )
    day_of_week = models.IntegerField(choices=DayOfWeek.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_day_off = models.BooleanField(default=False)

    class Meta:
        ordering = ['day_of_week', 'start_time']
        unique_together = ('provider', 'day_of_week')

    def clean(self):
        if not self.is_day_off and self.start_time >= self.end_time:
            raise ValidationError("Start time must be strictly before end time.")

    def __str__(self):
        if self.is_day_off:
            return f"{self.provider.name} - {self.get_day_of_week_display()}: Day Off"
        return f"{self.provider.name} - {self.get_day_of_week_display()}: {self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"


class TimeOff(models.Model):
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='time_offs'
    )
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_datetime']

    def clean(self):
        if self.start_datetime >= self.end_datetime:
            raise ValidationError("Start datetime must be strictly before end datetime.")

    def __str__(self):
        return f"{self.provider.name} Time Off: {self.start_datetime} to {self.end_datetime}"
