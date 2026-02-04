from stravalib import Client
from .models import StravaToken, Athlete, Month
from django.contrib.sites.models import Site
from django.conf import settings
from datetime import date
import calendar


class StravaClient():
    """
    Manage integration to Strava
    """

    client = None
    strava_token = None
    request = None

    def __init__(self):
        self.client = Client()
        self.strava_token = StravaToken.objects.first()

    def get_auth_url(self):
        """
        Generate the redirect URL to start the auth process
        """
        site = Site.objects.get_current() 
        redirect_url = 'http%s://%s/strava/callback' % ('s' if not settings.IS_LOCAL else '', site.domain)
        return self.client.authorization_url(
            client_id=self.strava_token.client_id,
            redirect_uri=redirect_url
        )

    def auth_callback(self, code):
        """
        Process auth callback and save access and refresh tokens
        """
        token_response = self.client.exchange_code_for_token(
            client_id=self.strava_token.client_id, 
            client_secret=self.strava_token.client_secret, 
            code=code
        )
        self.strava_token.access_token = token_response["access_token"]
        self.strava_token.refresh_token = token_response["refresh_token"]
        self.strava_token.save()

    def refresh_token(self):
        """
        Refresh the token with Strava
        """
        token_response = self.client.refresh_access_token(
            client_id=self.strava_token.client_id, 
            client_secret=self.strava_token.client_secret, 
            refresh_token=self.strava_token.refresh_token,
        )
        self.strava_token.access_token = token_response["access_token"]
        self.strava_token.refresh_token = token_response["refresh_token"]
        self.strava_token.save()


    def sync_activities(self, month_slug):
        """
        For a given month, sync the activities
        """

        # always refresh the token, just because I'm lazy
        self.refresh_token()

        month_record = Month.objects.get(slug=month_slug)
        start_date = month_record.date.strftime('%Y-%m-%d')
        num_days_in_month = calendar.monthrange(month_record.date.year, month_record.date.month)
        end_date = date(month_record.date.year, month_record.date.month, num_days_in_month[1]).strftime('%Y-%m-%d')
        print(start_date)
        print(end_date)

        # Refresh activities for each ath,ete
        for athlete in Athlete.objects.all():
            for activity in self.client.get_activities(after=start_date, before=end_date):
                print(activity)


