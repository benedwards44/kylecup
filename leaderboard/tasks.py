from leaderboard.strava import StravaClient
from django.utils import timezone
from celery import shared_task

@shared_task
def sync_activities():
    """
    Syncs activities from Strava for the current month. This is intended to be run as a scheduled task.
    """
    client = StravaClient()
    client.sync_activities(timezone.now().strftime("%b").lower())