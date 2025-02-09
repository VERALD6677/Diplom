from typing import Type

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import post_save
from django.dispatch import receiver, Signal
from django_rest_passwordreset.signals import reset_password_token_created

from backend.models import ConfirmEmailToken, User
from backend.tasks import send_email

new_user_registered = Signal()

new_order = Signal()


@receiver(reset_password_token_created)
def password_reset_token_created(sender, instance, reset_password_token, **kwargs):
    """
    Отправляем письмо с токеном для сброса пароля
    When a token is created, an e-mail needs to be sent to the user
    :param sender: View Class that sent the signal
    :param instance: View Instance that sent the signal
    :param reset_password_token: Token Model Object
    :param kwargs:
    :return:
    """
    # send an e-mail to the user
    title = f"Password Reset Token for {reset_password_token.user}"
    message = reset_password_token.key
    email = [reset_password_token.user.email]
    from_email = settings.EMAIL_HOST_USER
    send_email(
        title=title,
        message=message,
        from_email=from_email,
        email=email
    )


@receiver(post_save, sender=User)
def new_user_registered_signal(sender: Type[User], instance: User, created: bool, **kwargs):
    """
     отправляем письмо с подтрердждением почты
    """
    if created and not instance.is_active:
        # send an e-mail to the user
        token, _ = ConfirmEmailToken.objects.get_or_create(user_id=instance.pk)

        title = f"Password Reset Token for {instance.email}"
        message = token.key
        email = [instance.email]
        from_email = settings.EMAIL_HOST_USER
        send_email(
            title=title,
            message=message,
            from_email=from_email,
            email=email
        )


@receiver(new_order)
def new_order_signal(user_id, **kwargs):
    """
    отправяем письмо при изменении статуса заказа
    """
    # send an e-mail to the user
    user = User.objects.get(id=user_id)

    title = f"Обновление статуса заказа"
    message = f'Заказ сформирован'
    email = [user.email]
    from_email = settings.EMAIL_HOST_USER
    send_email(
        title=title,
        message=message,
        from_email=from_email,
        email=email
    )

