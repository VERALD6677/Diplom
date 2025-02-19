from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth.models import User
from .models import Product
import json

class ThrottleTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client.login(username='testuser', password='password')
        self.product_data = {'name': 'Test Product', 'price': 10.00, 'description': 'Test Description'}
        self.url = reverse('product-list-create')  #  URL для создания продуктов

    def test_throttled_create_product(self):
        """
        Проверяет, что пользователь подвергается тротлингу при попытке создать слишком много продуктов.
        """
        for i in range(20):
            response = self.client.post(self.url, data=self.product_data, format='json')

        #  Последний запрос должен быть отклонен из-за тротлинга
        response = self.client.post(self.url, data=self.product_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
