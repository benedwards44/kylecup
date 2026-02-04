from django.shortcuts import redirect
from django.views import View
from django.views.generic.detail import DetailView
from . import models
from datetime import datetime
from leaderboard.strava import StravaClient


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
        client = StravaClient()
        return redirect(client.get_auth_url())
    
    def get_strava_token_record(self):
        return models.StravaToken.objects.first()
    


class StravaCallbackView(View):
    """
    Handle callback from Strava and store token
    """
    
    def get(self, request, *args, **kwargs):
        client = StravaClient()
        client.auth_callback(request.GET.get('code'))
        return redirect('index')
    
    def get_strava_token_record(self):
        return models.StravaToken.objects.first()
    

class StravaSyncView(View):
    """
    Trigger sync to Strava for a given month
    """

    def get(self, request, *args, **kwargs):
        """
        Sync the activity records for the given month
        """
        client = StravaClient()
        client.sync_activities()
        return redirect('month', slug=self.kwargs['month'])
    