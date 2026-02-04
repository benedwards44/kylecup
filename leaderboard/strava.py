from stravalib import Client
from .models import Athlete, Month, Activity, AthleteMonthSummary
from django.contrib.sites.models import Site
from django.conf import settings
from datetime import date
from django.conf import settings
import calendar


class StravaClient():
    """
    Manage integration to Strava
    """

    client = None
    access_token = None

    def __init__(self, access_token=None):
        self.client = Client(access_token=access_token)
        

    def get_auth_url(self):
        """
        Generate the redirect URL to start the auth process
        """
        site = Site.objects.get_current() 
        redirect_url = 'http%s://%s/strava/callback' % ('s' if not settings.IS_LOCAL else '', site.domain)
        return self.client.authorization_url(
            client_id=settings.STRAVA_CLIENT_ID,
            redirect_uri=redirect_url
        )

    def auth_callback(self, code):
        """
        Process auth callback and save access and refresh tokens
        """
        token_response = self.client.exchange_code_for_token(
            client_id=settings.STRAVA_CLIENT_ID, 
            client_secret=settings.STRAVA_CLIENT_SECRET, 
            code=code
        )
        self.client = Client(access_token=token_response["access_token"])
        strava_athlete = self.client.get_athlete()
        athlete = Athlete.objects.get(strava_id=strava_athlete.id)
        athlete.strava_access_token = token_response["access_token"]
        athlete.strava_refresh_token = token_response["refresh_token"]
        athlete.save()


    def refresh_token(self, athlete):
        """
        Refresh the token with Strava
        """
        token_response = self.client.refresh_access_token(
            client_id=settings.STRAVA_CLIENT_ID, 
            client_secret=settings.STRAVA_CLIENT_SECRET, 
            refresh_token=athlete.refresh_token,
        )
        athlete.strava_access_token = token_response["access_token"]
        athlete.strava_refresh_token = token_response["refresh_token"]
        athlete.save()


    def sync_activities(self, month_slug):
        """
        For a given month, sync the activities
        """

        month_record = Month.objects.get(slug=month_slug)
        start_date = month_record.date.strftime('%Y-%m-%d')
        num_days_in_month = calendar.monthrange(month_record.date.year, month_record.date.month)
        end_date = date(month_record.date.year, month_record.date.month, num_days_in_month[1]).strftime('%Y-%m-%d')

        # Refresh activities for each ath,ete
        for athlete in Athlete.objects.filter(access_token__isnull=False):
            self.refresh_token(athlete)
            self.client = Client(access_token=athlete.strava_access_token)
            athlete_month_summary = None
            try:
                athlete_month_summary = AthleteMonthSummary.objects.get(athlete=athlete, month=month_record)
            except AthleteMonthSummary.DoesNotExist:
                athlete_month_summary = AthleteMonthSummary(
                    athlete=athlete, 
                    month=month_record
                )
                athlete_month_summary.save()
            for activity in self.client.get_activities(after=start_date, before=end_date):
                # Only save run
                if activity.type == 'Run':
                    try:
                        existing_activity = Activity.objects.get(strava_id=activity.id)
                    except Activity.DoesNotExist:
                        # Create the new activity
                        new_activity = Activity()
                        new_activity.strava_id = activity.id 
                        new_activity.distance = activity.distance / 100
                        new_activity.pace = activity.average_speed
                        new_activity.athlete_month_summary = athlete_month_summary
                        new_activity.save()




