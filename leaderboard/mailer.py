from django.conf import settings
from django.core.mail import send_mail


def send_email(subject, message):
    """
    Send an email to the site admins
    """
    return send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email for name, email in settings.ADMINS],
    )
