import threading
from datetime import date, datetime, time, timedelta
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APITransactionTestCase

from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services import AvailabilityService, BookingService
from apps.services.models import DayOfWeek, Provider, Service, TimeOff, WorkingHour

User = get_user_model()


class BookingSystemTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email='admin@example.com',
            username='admin',
            password='AdminPassword123!',
            role='ADMIN'
        )
        self.customer1 = User.objects.create_user(
            email='customer1@example.com',
            username='customer1',
            password='Password123!',
            role='CUSTOMER'
        )
        self.customer2 = User.objects.create_user(
            email='customer2@example.com',
            username='customer2',
            password='Password123!',
            role='CUSTOMER'
        )
        self.provider_user = User.objects.create_user(
            email='provider@example.com',
            username='provider',
            password='Password123!',
            role='PROVIDER'
        )

        self.service = Service.objects.create(
            name='Massage Therapy',
            description='Relaxing full body massage',
            duration_minutes=60,
            price='75.00',
            buffer_time_minutes=15
        )

        self.provider = Provider.objects.create(
            user=self.provider_user,
            name='Therapist Jane',
            email='jane@example.com',
            timezone='UTC'
        )
        self.provider.services.add(self.service)

        # Configure working hours for all days 09:00 - 18:00
        for day in range(7):
            WorkingHour.objects.create(
                provider=self.provider,
                day_of_week=day,
                start_time=time(9, 0),
                end_time=time(18, 0),
                is_day_off=False
            )

    def test_availability_slot_generation(self):
        # Target date tomorrow
        target_date = (timezone.now() + timedelta(days=1)).date()
        slots = AvailabilityService.get_available_slots(
            service=self.service,
            provider=self.provider,
            target_date=target_date,
            slot_interval_minutes=60
        )
        self.assertTrue(len(slots) > 0)
        first_slot = slots[0]
        self.assertEqual(first_slot['provider_id'], self.provider.id)
        self.assertEqual(first_slot['service_id'], self.service.id)

    def test_availability_api_endpoint(self):
        target_date = (timezone.now() + timedelta(days=2)).date()
        url = reverse('availability_search')
        response = self.client.get(url, {
            'service_id': self.service.id,
            'provider_id': self.provider.id,
            'date': str(target_date),
            'slot_interval': 60
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        self.assertTrue(len(response.data) > 0)

    def test_create_booking_success(self):
        self.client.force_authenticate(user=self.customer1)
        url = reverse('booking-list')
        future_dt = (timezone.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)

        data = {
            'service_id': self.service.id,
            'provider_id': self.provider.id,
            'start_time': future_dt.isoformat(),
            'customer_notes': 'Please be gentle'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], BookingStatus.PENDING)
        self.assertEqual(response.data['total_price'], '75.00')
        self.assertEqual(response.data['customer']['email'], self.customer1.email)

    def test_prevent_double_booking_same_slot(self):
        future_dt = (timezone.now() + timedelta(days=2)).replace(hour=11, minute=0, second=0, microsecond=0)

        # 1st booking succeeds
        self.client.force_authenticate(user=self.customer1)
        url = reverse('booking-list')
        data = {
            'service_id': self.service.id,
            'provider_id': self.provider.id,
            'start_time': future_dt.isoformat(),
        }
        res1 = self.client.post(url, data, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        # 2nd booking for same slot by customer 2 must fail
        self.client.force_authenticate(user=self.customer2)
        res2 = self.client.post(url, data, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('available', str(res2.data))

    def test_booking_outside_working_hours_fails(self):
        self.client.force_authenticate(user=self.customer1)
        url = reverse('booking-list')
        # 04:00 AM is outside 09:00 - 18:00
        outside_dt = (timezone.now() + timedelta(days=1)).replace(hour=4, minute=0, second=0, microsecond=0)
        data = {
            'service_id': self.service.id,
            'provider_id': self.provider.id,
            'start_time': outside_dt.isoformat(),
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_booking_in_past_fails(self):
        self.client.force_authenticate(user=self.customer1)
        url = reverse('booking-list')
        past_dt = timezone.now() - timedelta(days=1)
        data = {
            'service_id': self.service.id,
            'provider_id': self.provider.id,
            'start_time': past_dt.isoformat(),
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_booking_cancellation_policy(self):
        # Create booking 1 hour from now (less than 2 hours min cancellation policy)
        soon_dt = timezone.now() + timedelta(hours=1, minutes=10)
        booking = Booking.objects.create(
            customer=self.customer1,
            provider=self.provider,
            service=self.service,
            start_time=soon_dt,
            end_time=soon_dt + timedelta(minutes=60),
            status=BookingStatus.PENDING,
            total_price='75.00'
        )

        self.client.force_authenticate(user=self.customer1)
        cancel_url = reverse('booking-cancel', kwargs={'pk': booking.id})
        cancel_res = self.client.post(cancel_url, {'reason': 'Cannot make it'}, format='json')
        # Customer cannot cancel within 2 hours
        self.assertEqual(cancel_res.status_code, status.HTTP_400_BAD_REQUEST)

        # Admin CAN cancel anytime
        self.client.force_authenticate(user=self.admin_user)
        admin_cancel_res = self.client.post(cancel_url, {'reason': 'Admin override'}, format='json')
        self.assertEqual(admin_cancel_res.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_cancel_res.data['status'], BookingStatus.CANCELLED)

    def test_provider_confirm_and_complete_booking(self):
        future_dt = timezone.now() + timedelta(days=3)
        booking = Booking.objects.create(
            customer=self.customer1,
            provider=self.provider,
            service=self.service,
            start_time=future_dt,
            end_time=future_dt + timedelta(minutes=60),
            status=BookingStatus.PENDING,
            total_price='75.00'
        )

        # Provider confirms
        self.client.force_authenticate(user=self.provider_user)
        confirm_url = reverse('booking-confirm', kwargs={'pk': booking.id})
        confirm_res = self.client.post(confirm_url)
        self.assertEqual(confirm_res.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_res.data['status'], BookingStatus.CONFIRMED)

        # Provider completes
        complete_url = reverse('booking-complete', kwargs={'pk': booking.id})
        complete_res = self.client.post(complete_url)
        self.assertEqual(complete_res.status_code, status.HTTP_200_OK)
        self.assertEqual(complete_res.data['status'], BookingStatus.COMPLETED)

    def test_booking_history_visibility_and_filters(self):
        b1 = Booking.objects.create(
            customer=self.customer1,
            provider=self.provider,
            service=self.service,
            start_time=timezone.now() + timedelta(days=4),
            end_time=timezone.now() + timedelta(days=4, hours=1),
            status=BookingStatus.PENDING,
            total_price='75.00'
        )
        b2 = Booking.objects.create(
            customer=self.customer2,
            provider=self.provider,
            service=self.service,
            start_time=timezone.now() + timedelta(days=5),
            end_time=timezone.now() + timedelta(days=5, hours=1),
            status=BookingStatus.CONFIRMED,
            total_price='75.00'
        )
        # Booking where provider_user is the customer
        b_provider_cust = Booking.objects.create(
            customer=self.provider_user,
            provider=self.provider,
            service=self.service,
            start_time=timezone.now() + timedelta(days=6),
            end_time=timezone.now() + timedelta(days=6, hours=1),
            status=BookingStatus.CONFIRMED,
            total_price='75.00'
        )

        # Customer 1 can only see b1
        self.client.force_authenticate(user=self.customer1)
        url = reverse('booking-list')
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [item['id'] for item in res.data['results']]
        self.assertIn(b1.id, ids)
        self.assertNotIn(b2.id, ids)
        self.assertNotIn(b_provider_cust.id, ids)

        # Provider user by default sees bookings assigned to their provider profile
        self.client.force_authenticate(user=self.provider_user)
        res_prov = self.client.get(url)
        self.assertEqual(res_prov.status_code, status.HTTP_200_OK)
        prov_ids = [item['id'] for item in res_prov.data['results']]
        self.assertIn(b1.id, prov_ids)
        self.assertIn(b2.id, prov_ids)
        self.assertIn(b_provider_cust.id, prov_ids)

        # Provider can explicitly view bookings where they are the customer
        res_prov_customer = self.client.get(url, {'as_customer': 'true'})
        self.assertEqual(res_prov_customer.status_code, status.HTTP_200_OK)
        prov_customer_ids = [item['id'] for item in res_prov_customer.data['results']]
        self.assertEqual(prov_customer_ids, [b_provider_cust.id])

        # Admin can see all
        self.client.force_authenticate(user=self.admin_user)
        res_admin = self.client.get(url)
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        admin_ids = [item['id'] for item in res_admin.data['results']]
        self.assertIn(b1.id, admin_ids)
        self.assertIn(b2.id, admin_ids)
        self.assertIn(b_provider_cust.id, admin_ids)

        # Admin with ?my_bookings=true sees only their own bookings
        res_admin_my = self.client.get(url, {'my_bookings': 'true'})
        self.assertEqual(res_admin_my.status_code, status.HTTP_200_OK)
        admin_my_ids = [item['id'] for item in res_admin_my.data['results']]
        self.assertEqual(admin_my_ids, [])

    def test_assigned_provider_can_cancel_booking(self):
        future_dt = timezone.now() + timedelta(days=3)
        booking = Booking.objects.create(
            customer=self.customer1,
            provider=self.provider,
            service=self.service,
            start_time=future_dt,
            end_time=future_dt + timedelta(minutes=60),
            status=BookingStatus.PENDING,
            total_price='75.00'
        )

        self.client.force_authenticate(user=self.provider_user)
        cancel_url = reverse('booking-cancel', kwargs={'pk': booking.id})
        response = self.client.post(cancel_url, {'reason': 'Provider unavailable'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], BookingStatus.CANCELLED)
        booking.refresh_from_db()
        self.assertEqual(booking.cancelled_by_id, self.provider_user.id)


class ConcurrentBookingTests(APITransactionTestCase):
    def setUp(self):
        self.customer1 = User.objects.create_user(
            email='c1@example.com',
            username='c1',
            password='Password123!',
            role='CUSTOMER'
        )
        self.customer2 = User.objects.create_user(
            email='c2@example.com',
            username='c2',
            password='Password123!',
            role='CUSTOMER'
        )
        self.service = Service.objects.create(
            name='Haircut',
            duration_minutes=30,
            price='30.00'
        )
        self.provider = Provider.objects.create(
            name='Barber Bob',
            email='bob@example.com',
            timezone='UTC'
        )
        self.provider.services.add(self.service)

        for day in range(7):
            WorkingHour.objects.create(
                provider=self.provider,
                day_of_week=day,
                start_time=time(9, 0),
                end_time=time(18, 0),
                is_day_off=False
            )

    def test_concurrent_booking_race_condition(self):
        target_dt = (timezone.now() + timedelta(days=5)).replace(hour=14, minute=0, second=0, microsecond=0)
        results = []
        errors = []

        def book_slot(user):
            from django.db import connection
            try:
                booking = BookingService.create_booking(
                    customer=user,
                    service=self.service,
                    provider=self.provider,
                    start_time=target_dt
                )
                results.append(booking)
            except Exception as e:
                errors.append(e)
            finally:
                connection.close()

        t1 = threading.Thread(target=book_slot, args=(self.customer1,))
        t2 = threading.Thread(target=book_slot, args=(self.customer2,))

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        # Exactly one thread succeeds, and the other gets rejected
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertEqual(Booking.objects.filter(provider=self.provider, start_time=target_dt).count(), 1)
