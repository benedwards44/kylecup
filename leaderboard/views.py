from django.shortcuts import redirect
from django.views import View
from django.views.generic.detail import DetailView
from . import models
from datetime import datetime
from stravalib import Client
from django.contrib.sites.shortcuts import get_current_site


class IndexView(View):
    """
    Redirect straight to relevant month
    """
    def get(self, request, *args, **kwargs):
        return redirect('month', slug=datetime.now().strftime("%b").lower())


class MonthView(DetailView):
    """
    The month view
    """

    model = models.Month
    template_name = 'month.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["months"] = models.Month.objects.all()
        context["activities"] = models.Activity.objects.filter(athlete_month_summary__month=self.get_object())
        context["athletes"] = self.athletes_ordered()
        return context
    
    def athletes_ordered(self):
        athletes = models.AthleteMonthSummary.objects.filter(month=self.get_object())
        return sorted(athletes, key=lambda athlete: athlete.total_distance(), reverse=True)



class StravaConnectView(View):
    """
    Initiate authorisation flow with Strava
    """
    def get(self, request, *args, **kwargs):
        client = Client()
        redirect_url = '%s/strava/callback' % get_current_site(request).domain
        url = client.authorization_url(
            client_id=self.get_strava_token_record().client_id,
            redirect_uri=redirect_url
        )
        return redirect(url)
    
    def get_strava_token_record(self):
        return models.StravaToken.objects.first()
    


class StravaCallbackView(View):
    """
    Handle callback from Strava and store token
    """
    
    def get(self, request, *args, **kwargs):
        client = Client()
        strava_token = self.get_strava_token_record()
        token_response = client.exchange_code_for_token(
            client_id=strava_token.client_id, 
            client_secret=strava_token.client_secret, 
            code=request.GET.get('code')
        )
        strava_token.access_token = token_response["access_token"]
        strava_token.refresh_token = token_response["refresh_token"]
        strava_token.save()
        return redirect('index')
    
    def get_strava_token_record(self):
        return models.StravaToken.objects.first()
    

class StravaSyncView(View):
    """
    Trigger sync to Strava for a given month
    """
    
    def get(self, request, *args, **kwargs):
        return redirect('index')
    