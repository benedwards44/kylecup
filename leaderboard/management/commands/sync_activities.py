from django.core.management.base import BaseCommand
from leaderboard.strava import StravaClient
from django.utils import timezone

class Command(BaseCommand):
    def handle(self, *args, **options):
        """
        Sync activities from Strava for current month
        """
        client = StravaClient()
        client.sync_activities(timezone.now().strftime("%b").lower())

        