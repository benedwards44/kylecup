import requests
from django.conf import settings

def send_email(subject, message):
    """
    Send an email using Mailgun API
    """
    return requests.post(
        "https://api.mailgun.net/v3/mg.edwards.nz/messages",
        auth=("api", settings.MAILGUN_API_KEY),
        data={
            "from": settings.DEFAULT_FROM_EMAIL,
            "to": "Ben Edwards <ben@edwards.nz>",
            "subject": subject,
            "text": message,
        },
    )