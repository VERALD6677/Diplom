from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from backend.models import User, Shop, Category, Product, ProductInfo, Parameter, ProductParameter, Order, OrderItem, \
    Contact, ConfirmEmailToken


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    Панель управления пользователями
    """
    model = User

    fieldsets = (
        (None, {'fields': ('email', 'password', 'type')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'company', 'position')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    list_display = ('email', 'first_name', 'last_name', 'company', 'position', 'type')
    list_filter = ('type', 'is_active', 'is_staff', 'is_superuser',)


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    model = Shop
    fieldsets = (
        (None, {'fields': ('name', 'state')}),
        ('Advanced options', {'classes': ('collapse',), 'fields': ('url', 'user')}),
    )
    list_display = ('name', 'user', 'url', 'state',)
    list_filter = ('state',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    pass


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_filter = ('category',)
    list_display = ('name', 'category')


@admin.register(ProductInfo)
class ProductInfoAdmin(admin.ModelAdmin):
    list_filter = ('shop', 'model')
    list_display = ('product', 'model', 'shop', 'quantity', 'price', 'price_rrc',)


@admin.register(Parameter)
class ParameterAdmin(admin.ModelAdmin):
    pass


@admin.register(ProductParameter)
class ProductParameterAdmin(admin.ModelAdmin):
    list_filter = ('parameter',)
    list_display = ('product_info', 'parameter', 'value')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_filter = ('state',)
    list_display = ('user', 'dt', 'state', 'contact')


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product_info', 'quantity')


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'street', 'house', 'structure', 'building', 'apartment', 'phone',)


@admin.register(ConfirmEmailToken)
class ConfirmEmailTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'key', 'created_at',)
