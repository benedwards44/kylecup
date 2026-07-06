import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class MailgunEmailBackend(BaseEmailBackend):
    """
    Django email backend that sends via the Mailgun API instead of SMTP
    """

    api_url = "https://api.mailgun.net/v3/%s/messages"

    def send_messages(self, email_messages):
        sent_count = 0
        for message in email_messages:
            if not message.recipients():
                continue
            try:
                data = {
                    "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
                    "to": message.to,
                    "cc": message.cc,
                    "bcc": message.bcc,
                    "subject": message.subject,
                    "text": message.body,
                }
                for content, mimetype in getattr(message, "alternatives", []):
                    if mimetype == "text/html":
                        data["html"] = content
                response = requests.post(
                    self.api_url % settings.MAILGUN_DOMAIN,
                    auth=("api", settings.MAILGUN_API_KEY),
                    data=data,
                )
                response.raise_for_status()
                sent_count += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent_count
