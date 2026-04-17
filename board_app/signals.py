from django.conf import settings
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Response


@receiver(post_save, sender=Response)
def notify_about_new_response(sender, instance, created, **kwargs):
    if created:
        ad_owner_email = instance.ad.author.email
        send_mail(
            subject=f"Новый отклик на объявление: {instance.ad.title}",
            message=(
                f"На ваше объявление '{instance.ad.title}' пришёл новый отклик.\n\n"
                f"Текст отклика:\n{instance.text}\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[ad_owner_email],
            fail_silently=True,
        )