from leaderboard.strava import StravaClient
from django.utils import timezone
from celery import shared_task
from django.core.mail import send_mail

@shared_task
def sync_activities():
    """
    Syncs activities from Strava for the current month. This is intended to be run as a scheduled task.
    """
    client = StravaClient()
    client.sync_activities(timezone.now().strftime("%b").lower())
    send_mail(
        subject='Successfully ran Strava sync.',
        message='Yay, it synced',
        from_email=None,
        recipient_list=['ben@edwards.nz'],
    )