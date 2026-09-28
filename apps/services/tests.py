from datetime import time
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.services.models import DayOfWeek, Provider, Service, WorkingHour

User = get_user_model()


class ServiceAndProviderTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email='admin@example.com',
            username='admin',
            password='AdminPassword123!',
            role='ADMIN'
        )
        self.customer_user = User.objects.create_user(
            email='customer@example.com',
            username='customer',
            password='CustomerPassword123!',
            role='CUSTOMER'
        )
        self.provider_user = User.objects.create_user(
            email='doctor@example.com',
            username='doctor',
            password='DoctorPassword123!',
            role='PROVIDER'
        )

    def test_service_crud_permissions(self):
        # Public cannot create service
        url = reverse('service-list')
        data = {
            'name': 'Dental Cleaning',
            'description': 'Full dental hygiene treatment',
            'duration_minutes': 45,
            'price': '80.00',
            'buffer_time_minutes': 15,
        }
        res_unauth = self.client.post(url, data, format='json')
        self.assertEqual(res_unauth.status_code, status.HTTP_401_UNAUTHORIZED)

        # Customer cannot create service
        self.client.force_authenticate(user=self.customer_user)
        res_cust = self.client.post(url, data, format='json')
        self.assertEqual(res_cust.status_code, status.HTTP_403_FORBIDDEN)

        # Admin can create service
        self.client.force_authenticate(user=self.admin_user)
        res_admin = self.client.post(url, data, format='json')
        self.assertEqual(res_admin.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_admin.data['name'], 'Dental Cleaning')

    def test_provider_creation_and_working_hours(self):
        # Admin creates service
        service = Service.objects.create(
            name='Consultation',
            duration_minutes=30,
            price='50.00'
        )

        # Admin creates provider
        self.client.force_authenticate(user=self.admin_user)
        prov_url = reverse('provider-list')
        prov_data = {
            'user': self.provider_user.id,
            'name': 'Dr. Smith',
            'email': 'doctor@example.com',
            'phone_number': '+1122334455',
            'service_ids': [service.id],
            'timezone': 'UTC'
        }
        res = self.client.post(prov_url, prov_data, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        provider_id = res.data['id']

        # Add Working Hours
        wh_url = reverse('working-hour-list')
        wh_data = {
            'provider': provider_id,
            'day_of_week': DayOfWeek.MONDAY,
            'start_time': '09:00:00',
            'end_time': '17:00:00',
            'is_day_off': False
        }
        wh_res = self.client.post(wh_url, wh_data, format='json')
        self.assertEqual(wh_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(wh_res.data['day_of_week_display'], 'Monday')

    def test_working_hour_validation_start_before_end(self):
        provider = Provider.objects.create(name='Provider 1', email='p1@example.com')
        self.client.force_authenticate(user=self.admin_user)
        wh_url = reverse('working-hour-list')
        wh_data = {
            'provider': provider.id,
            'day_of_week': DayOfWeek.TUESDAY,
            'start_time': '17:00:00',
            'end_time': '09:00:00',  # invalid
            'is_day_off': False
        }
        wh_res = self.client.post(wh_url, wh_data, format='json')
        self.assertEqual(wh_res.status_code, status.HTTP_400_BAD_REQUEST)
