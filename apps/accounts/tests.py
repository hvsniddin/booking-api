from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class AuthTests(APITestCase):
    def test_register_user_success(self):
        url = reverse('auth_register')
        data = {
            'email': 'customer@example.com',
            'username': 'customer1',
            'password': 'StrongPassword123!',
            'password_confirm': 'StrongPassword123!',
            'role': 'CUSTOMER',
            'phone_number': '+1234567890',
            'timezone': 'America/New_York'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])
        self.assertEqual(response.data['user']['email'], 'customer@example.com')
        self.assertEqual(response.data['user']['role'], 'CUSTOMER')

    def test_register_password_mismatch(self):
        url = reverse('auth_register')
        data = {
            'email': 'mismatch@example.com',
            'username': 'mismatch',
            'password': 'StrongPassword123!',
            'password_confirm': 'DifferentPassword123!',
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_login_and_token_refresh(self):
        user = User.objects.create_user(
            email='testlogin@example.com',
            username='testlogin',
            password='TestPassword123!'
        )
        login_url = reverse('token_obtain_pair')
        response = self.client.post(login_url, {
            'email': 'testlogin@example.com',
            'password': 'TestPassword123!'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

        # Refresh token
        refresh_url = reverse('token_refresh')
        refresh_response = self.client.post(refresh_url, {
            'refresh': response.data['refresh']
        }, format='json')
        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        self.assertIn('access', refresh_response.data)

    def test_profile_endpoint(self):
        user = User.objects.create_user(
            email='profile@example.com',
            username='profileuser',
            password='Password123!',
            role='CUSTOMER'
        )
        self.client.force_authenticate(user=user)
        url = reverse('user_profile')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'profile@example.com')

        # Update profile
        patch_response = self.client.patch(url, {'first_name': 'John'}, format='json')
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.data['first_name'], 'John')
