from distutils.util import strtobool
from rest_framework.request import Request
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError
from django.db.models import Q, Sum, F
from django.http import JsonResponse
from requests import get
from rest_framework.authtoken.models import Token
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from ujson import loads as load_json
from yaml import load as load_yaml, Loader

from backend.models import Shop, Category, Product, ProductInfo, Parameter, ProductParameter, Order, OrderItem, \
    Contact, ConfirmEmailToken
from backend.serializers import UserSerializer, CategorySerializer, ShopSerializer, ProductInfoSerializer, \
    OrderItemSerializer, OrderSerializer, ContactSerializer
from backend.signals import new_user_registered, new_order
from backend.tasks import do_import
from django.urls import reverse
from rest_framework.test import APITestCase
from backend.models import User, ConfirmEmailToken, Order, OrderItem, ProductInfo
from rest_framework import throttling

class RegisterAccount(APIView):
    throttle_classes = [throttling.UserRateThrottle]  
   

class BasketView(APIView):
    throttle_classes = [throttling.UserRateThrottle]
   


class UserRegistrationTests(APITestCase):
    def test_successful_registration(self):
        data = {
            "first_name": "Иван",
            "last_name": "Петров",
            "email": "test@example.com",
            "password": "SecurePass123!",
            "company": "TestCompany",
            "position": "Manager"
        }
        response = self.client.post(reverse('user-register'), data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(email=data['email']).exists())

    def test_password_validation_error(self):
        data = {
            "first_name": "Иван",
            "last_name": "Петров",
            "email": "test@example.com",
            "password": "123",
            "company": "TestCompany",
            "position": "Manager"
        }
        response = self.client.post(reverse('user-register'), data)
        self.assertEqual(response.json()['Status'], False)
        self.assertIn('password', response.json()['Errors'])


class UserLoginTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='user@example.com',
            password='strongpass123',
            is_active=True
        )

    def test_successful_login(self):
        data = {"email": "user@example.com", "password": "strongpass123"}
        response = self.client.post(reverse('user-login'), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Token', response.json())

    def test_invalid_credentials(self):
        data = {"email": "user@example.com", "password": "wrong"}
        response = self.client.post(reverse('user-login'), data)
        self.assertEqual(response.status_code, 400)


class BasketTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='user@example.com',
            password='password',
            is_active=True
        )
        cls.product = ProductInfo.objects.create(
            name="Test Product",
            quantity=10,
            price=100.00
        )

    def test_add_to_basket_authenticated(self):
        self.client.force_authenticate(user=self.user)
        items = [{"product_info": self.product.id, "quantity": 2}]
        response = self.client.post(
            reverse('basket'),
            {'items': str(items)},
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(OrderItem.objects.count(), 1)


class RegisterAccount(APIView):
    """
    Для регистрации покупателей
    """

    def post(self, request, *args, **kwargs):
        """
        Process a POST request and create a new user.

        Args:
            request (Request): The Django request object.

        Returns:
            JsonResponse: The response indicating the status of the operation and any errors.
        """
        # проверяем обязательные аргументы
        if {'first_name', 'last_name', 'email', 'password', 'company', 'position'}.issubset(request.data):

            # проверяем пароль на сложность
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                error_array = []
                for item in password_error:
                    error_array.append(item)
                return JsonResponse({'Status': False, 'Errors': {'password': error_array}})
            else:
                # проверяем данные для уникальности имени пользователя

                user_serializer = UserSerializer(data=request.data)
                if user_serializer.is_valid():
                    # сохраняем пользователя
                    user = user_serializer.save()
                    user.set_password(request.data['password'])
                    user.save()
                    return JsonResponse({'Status': True})
                else:
                    return JsonResponse({'Status': False, 'Errors': user_serializer.errors})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class ConfirmAccount(APIView):
    """
    Класс для подтверждения почтового адреса
    """

    def post(self, request, *args, **kwargs):
        """
        Подтверждает почтовый адрес пользователя.

        Args:
        - request (Request): The Django request object.

        Returns:
        - JsonResponse: The response indicating the status of the operation and any errors.
        """
        # проверяем обязательные аргументы
        if {'email', 'token'}.issubset(request.data):

            token = ConfirmEmailToken.objects.filter(user__email=request.data['email'],
                                                     key=request.data['token']).first()
            if token:
                token.user.is_active = True
                token.user.save()
                token.delete()
                return JsonResponse({'Status': True})
            else:
                return JsonResponse({'Status': False, 'Errors': 'Неправильно указан токен или email'})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class AccountDetails(APIView):
    """
    A class for managing user account details.

    Methods:
    - get: Retrieve the details of the authenticated user.
    - post: Update the account details of the authenticated user.

    Attributes:
    - None
    """

    def get(self, request: Request, *args, **kwargs):
        """
        Retrieve the details of the authenticated user.

        Args:
        - request (Request): The Django request object.

        Returns:
        - Response: The response containing the details of the authenticated user.
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        """
        Update the account details of the authenticated user.

        Args:
        - request (Request): The Django request object.

        Returns:
        - JsonResponse: The response indicating the status of the operation and any errors.
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if 'password' in request.data:
            # проверяем пароль на сложность
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                error_array = []
                for item in password_error:
                    error_array.append(item)
                return JsonResponse({'Status': False, 'Errors': {'password': error_array}})
            else:
                request.user.set_password(request.data['password'])

        # проверяем остальные данные
        user_serializer = UserSerializer(request.user, data=request.data, partial=True)
        if user_serializer.is_valid():
            user_serializer.save()
            return JsonResponse({'Status': True})
        else:
            return JsonResponse({'Status': False, 'Errors': user_serializer.errors})


class LoginAccount(APIView):
    """
    Класс для авторизации пользователей
    """

    def post(self, request, *args, **kwargs):
        """
        Authenticate a user.

        Args:
            request (Request): The Django request object.

        Returns:
            JsonResponse: The response indicating the status of the operation and any errors.
        """
        if {'email', 'password'}.issubset(request.data):
            user = authenticate(request, username=request.data['email'], password=request.data['password'])

            if user is not None:
                if user.is_active:
                    token, _ = Token.objects.get_or_create(user=user)

                    return JsonResponse({'Status': True, 'Token': token.key})

            return JsonResponse({'Status': False, 'Errors': 'Не удалось авторизовать'})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class CategoryView(ListAPIView):
    """
    Класс для просмотра категорий
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ShopView(ListAPIView):
    """
    Класс для просмотра списка магазинов
    """
    queryset = Shop.objects.filter(state=True)
    serializer_class = ShopSerializer


class ProductInfoView(APIView):
    """
    A class for searching products.

    Methods:
    - get: Retrieve the product information based on the specified filters.

    Attributes:
    - None
    """

    def get(self, request: Request, *args, **kwargs):
        """
        Retrieve the product information based on the specified filters.

        Args:
        - request (Request): The Django request object.

        Returns:
        - Response: The response containing the product information.
        """
        query = Q(shop__state=True)
        shop_id = request.query_params.get('shop_id')
        category_id = request.query_params.get('category_id')

        if shop_id:
            query = query & Q(shop_id=shop_id)

        if category_id:
            query = query & Q(product__category_id=category_id)

        # фильтруем и отбрасываем дуликаты
        queryset = ProductInfo.objects.filter(
            query).select_related(
            'shop', 'product__category').prefetch_related(
            'product_parameters__parameter').distinct()

        serializer = ProductInfoSerializer(queryset, many=True)

        return Response(serializer.data)


class BasketView(APIView):
    """
    A class for managing the user's shopping basket.

    Methods:
    - get: Retrieve the items in the user's basket.
    - post: Add an item to the user's basket.
    - put: Update the quantity of an item in the user's basket.
    - delete: Remove an item from the user's basket.

    Attributes:
    - None
    """

    def get(self, request, *args, **kwargs):
        """
        Retrieve the items in the user's basket.

        Args:
        - request (Request): The Django request object.

        Returns:
        - Response: The response containing the items in the user's basket.
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        basket = Order.objects.filter(
            user_id=request.user.id, state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(basket, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        """
        Add an items to the user's basket.

        Args:
        - request (Request): The Django request object.

        Returns:
        - JsonResponse: The response indicating the status of the operation and any errors.
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        items_sting = request.data.get('items')
        if items_sting:
            try:
                items_dict = load_json(items_sting)
            except ValueError:
                return JsonResponse({'Status': False, 'Errors': 'Неверный формат запроса'})
            else:
                basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
                objects_created = 0
                for order_item in items_dict:
                    order_item.update({'order': basket.id})
                    serializer = OrderItemSerializer(data=order_item)
                    if serializer.is_valid():
                        try:
                            serializer.save()
                        except IntegrityError as error:
                            return JsonResponse({'Status': False, 'Errors': str(error)})
                        else:
                            objects_created += 1

                    else:

                        return JsonResponse({'Status': False, 'Errors': serializer.errors})

                return JsonResponse({'Status': True, 'Создано объектов': objects_created})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})

    def delete(self, request, *args, **kwargs):
        """
        Remove items from the user's basket.

        Args:
        - request (Request): The Django request object.

        Returns:
        - JsonResponse: The response indicating the status of the operation and any errors.
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        items_sting = request.data.get('items')
        if items_sting:
            items_list = items_sting.split(',')
            basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
            objects_removed = 0
            for order_item_id in items_list:
                try:
                    order_item = OrderItem.objects.get(order_id=basket.id, id=order_item_id)
                except OrderItem.DoesNotExist:
                    return JsonResponse({'Status': False, 'Errors': f'Не найден order_item с id={order_item_id}'})
                else:
                    order_item.delete()
                    objects_removed += 1
            return JsonResponse({'Status': True, 'Удалено объектов': objects_removed})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class ContactView(APIView):
    """
    Класс для работы с контактами
    """

    def get(self, request, *args, **kwargs):
        """
        Получить мои контакты
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        contact = Contact.objects.filter(user_id=request.user.id)
        serializer = ContactSerializer(contact, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        """
        Добавить новый контакт
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        # проверяем обязательные аргументы
        if {'city', 'street', 'house', 'phone'}.issubset(request.data):
            request.data._mutable = True
            request.data['user'] = request.user.id
            serializer = ContactSerializer(data=request.data)

            if serializer.is_valid():
                serializer.save()
                return JsonResponse({'Status': True})
            else:
                return JsonResponse({'Status': False, 'Errors': serializer.errors})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})

    def delete(self, request, *args, **kwargs):
        """
        Удалить контакт
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        items_sting = request.data.get('items')
        if items_sting:
            items_list = items_sting.split(',')
            objects_removed = 0
            for contact_id in items_list:
                try:
                    contact = Contact.objects.get(user_id=request.user.id, id=contact_id)
                except Contact.DoesNotExist:
                    return JsonResponse({'Status': False, 'Errors': f'Не найден contact с id={contact_id}'})
                else:
                    contact.delete()
                    objects_removed += 1
            return JsonResponse({'Status': True, 'Удалено объектов': objects_removed})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class OrderView(APIView):
    """
    Класс для получения и размещения заказов пользователями
    """

    def get(self, request: Request, *args, **kwargs):
        """
        Получить список заказов
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        order = Order.objects.filter(
            user_id=request.user.id).exclude(state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        """
        Оформить заказ из корзины
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if {'id', 'contact'}.issubset(request.data):
            try:
                is_updated = Order.objects.filter(
                    user_id=request.user.id, id=request.data['id']).update(
                    contact_id=request.data['contact'],
                    state='new')
            except IntegrityError as error:
                return JsonResponse({'Status': False, 'Errors': str(error)})
            else:
                if is_updated:
                    new_order.send(request.user, order_id=request.data['id'])
                    return JsonResponse({'Status': True})
                else:
                    return JsonResponse({'Status': False, 'Errors': 'Не удалось изменить заказ'})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class PartnerUpdate(APIView):
    """
    Класс для обновления прайса от поставщика
    """

    def post(self, request, *args, **kwargs):
        """
        Update price list
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Only for shop'}, status=403)

        url = request.data.get('url')
        if url:
            validate_url = URLValidator()
            try:
                validate_url(url)
            except ValidationError as e:
                return JsonResponse({'Status': False, 'Error': str(e)})
            else:
                stream = get(url).content

                data = load_yaml(stream, Loader=Loader)

                shop, _ = Shop.objects.get_or_create(name=data['shop'], user_id=request.user.id)
                for category in data['categories']:
                    category_object, _ = Category.objects.get_or_create(id=category['id'], name=category['name'])
                    category_object.shops.add(shop.id)
                    category_object.save()
                ProductInfo.objects.filter(shop_id=shop.id).delete()
                for item in data['goods']:
                    product, _ = Product.objects.get_or_create(name=item['name'], category_id=item['category'])

                    product_info = ProductInfo.objects.create(shop_id=shop.id,
                                                               product_id=product.id,
                                                               external_id=item['id'],
                                                               model=item['model'],
                                                               price=item['price'],
                                                               price_rrc=item['price_rrc'],
                                                               quantity=item['quantity'])
                    for name, value in item['parameters'].items():
                        parameter_object, _ = Parameter.objects.get_or_create(name=name)
                        ProductParameter.objects.create(product_info_id=product_info.id,
                                                        parameter_id=parameter_object.id,
                                                        value=value)

                return JsonResponse({'Status': True})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class PartnerState(APIView):
    """
    Класс для работы со статусом поставщика
    """

    def post(self, request, *args, **kwargs):
        """
        Изменить статус магазина
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Only for shop'}, status=403)

        if {'state'}.issubset(request.data):
            try:
                state = strtobool(request.data['state'])
            except ValueError:
                return JsonResponse({'Status': False, 'Errors': 'Неправильно указан параметр'}, status=400)

            Shop.objects.filter(user_id=request.user.id).update(state=state)
            return JsonResponse({'Status': True})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class ContactView(APIView):
    """
    Класс для работы с контактами
    """

    def get(self, request, *args, **kwargs):
        """
        Получить мои контакты
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        contact = Contact.objects.filter(user_id=request.user.id)
        serializer = ContactSerializer(contact, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        """
        Добавить новый контакт
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        # проверяем обязательные аргументы
        if {'city', 'street', 'house', 'phone'}.issubset(request.data):
            request.data._mutable = True
            request.data['user'] = request.user.id
            serializer = ContactSerializer(data=request.data)

            if serializer.is_valid():
                serializer.save()
                return JsonResponse({'Status': True})
            else:
                return JsonResponse({'Status': False, 'Errors': serializer.errors})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})

    def delete(self, request, *args, **kwargs):
        """
        Удалить контакт
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        items_sting = request.data.get('items')
        if items_sting:
            items_list = items_sting.split(',')
            objects_removed = 0
            for contact_id in items_list:
                try:
                    contact = Contact.objects.get(user_id=request.user.id, id=contact_id)
                except Contact.DoesNotExist:
                    return JsonResponse({'Status': False, 'Errors': f'Не найден contact с id={contact_id}'})
                else:
                    contact.delete()
                    objects_removed += 1
            return JsonResponse({'Status': True, 'Удалено объектов': objects_removed})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class OrderView(APIView):
    """
    Класс для получения и размещения заказов пользователями
    """

    def get(self, request: Request, *args, **kwargs):
        """
        Получить список заказов
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        order = Order.objects.filter(
            user_id=request.user.id).exclude(state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        """
        Оформить заказ из корзины
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if {'id', 'contact'}.issubset(request.data):
            try:
                is_updated = Order.objects.filter(
                    user_id=request.user.id, id=request.data['id']).update(
                    contact_id=request.data['contact'],
                    state='new')
            except IntegrityError as error:
                return JsonResponse({'Status': False, 'Errors': str(error)})
            else:
                if is_updated:
                    new_order.send(request.user, order_id=request.data['id'])
                    return JsonResponse({'Status': True})
                else:
                    return JsonResponse({'Status': False, 'Errors': 'Не удалось изменить заказ'})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class PartnerUpdate(APIView):
    """
    Класс для обновления прайса от поставщика
    """

    def post(self, request, *args, **kwargs):
        """
        Update price list
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Only for shop'}, status=403)

        url = request.data.get('url')
        if url:
            validate_url = URLValidator()
            try:
                validate_url(url)
            except ValidationError as e:
                return JsonResponse({'Status': False, 'Error': str(e)})
            else:
                stream = get(url).content

                data = load_yaml(stream, Loader=Loader)

                shop, _ = Shop.objects.get_or_create(name=data['shop'], user_id=request.user.id)
                for category in data['categories']:
                    category_object, _ = Category.objects.get_or_create(id=category['id'], name=category['name'])
                    category_object.shops.add(shop.id)
                    category_object.save()
                ProductInfo.objects.filter(shop_id=shop.id).delete()
                for item in data['goods']:
                    product, _ = Product.objects.get_or_create(name=item['name'], category_id=item['category'])

                    product_info = ProductInfo.objects.create(shop_id=shop.id,
                                                               product_id=product.id,
                                                               external_id=item['id'],
                                                               model=item['model'],
                                                               price=item['price'],
                                                               price_rrc=item['price_rrc'],
                                                               quantity=item['quantity'])
                    for name, value in item['parameters'].items():
                        parameter_object, _ = Parameter.objects.get_or_create(name=name)
                        ProductParameter.objects.create(product_info_id=product_info.id,
                                                        parameter_id=parameter_object.id,
                                                        value=value)

                return JsonResponse({'Status': True})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class PartnerState(APIView):
    """
    Класс для работы со статусом поставщика
    """

    def post(self, request, *args, **kwargs):
        """
        Изменить статус магазина
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Only for shop'}, status=403)

        if {'state'}.issubset(request.data):
            try:
                state = strtobool(request.data['state'])
            except ValueError:
                return JsonResponse({'Status': False, 'Errors': 'Неправильно указан параметр'}, status=400)

            Shop.objects.filter(user_id=request.user.id).update(state=state)
            return JsonResponse({'Status': True})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})
