from django.shortcuts import redirect, render
from django.views import View
from django.views.generic.detail import DetailView
from django.core.mail import send_mail
from . import models
from datetime import timedelta
from django.utils import timezone
from leaderboard.strava import StravaClient


class IndexView(View):
    """
    Redirect straight to relevant month
    """
    def get(self, request, *args, **kwargs):
        return redirect('month', slug=timezone.now().strftime("%b").lower())


class MonthView(DetailView):
    """
    The month view
    """

    model = models.Month
    template_name = 'month.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        #self.resync_strava()
        context["months"] = models.Month.objects.all()
        context["activities"] = models.Activity.objects.filter(invalid=False, athlete_month_summary__month=self.get_object())
        context["athletes"] = self.athletes_ordered()
        return context
    
    def athletes_ordered(self):
        athletes = models.AthleteMonthSummary.objects.filter(month=self.get_object())
        return sorted(athletes, key=lambda athlete: athlete.total_distance(), reverse=True)
    
    def resync_strava(self):
        """
        If data is stale (eg. over an hour), resync
        """
        client = StravaClient()
        client.sync_activities_if_stale(self.get_object().slug)



class StravaConnectView(View):
    """
    Initiate authorisation flow with Strava
    """
    def get(self, request, *args, **kwargs):
        client = StravaClient()
        return redirect(client.get_auth_url())
    


class StravaCallbackView(View):
    """
    Handle callback from Strava and store token
    """
    
    def get(self, request, *args, **kwargs):
        client = StravaClient()
        client.auth_callback(request.GET.get('code'))
        return redirect('index')
    

class StravaSyncView(View):
    """
    Trigger sync to Strava for a given month
    """

    def get(self, request, *args, **kwargs):
        """
        Sync the activity records for the given month
        """
        client = StravaClient()
        client.sync_activities(self.kwargs['month'])
        return redirect('month', slug=self.kwargs['month'])


class PrivacyView(View):
    def get(self, request):
        return render(request, 'privacy.html', {
            'months': models.Month.objects.all(),
            'today': timezone.now().date(),
        })


class SupportView(View):
    def get(self, request):
        return render(request, 'support.html', {
            'months': models.Month.objects.all(),
        })

    def post(self, request):
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        message = request.POST.get('message', '').strip()

        if not all([name, email, message]):
            return render(request, 'support.html', {
                'months': models.Month.objects.all(),
                'error': 'Please fill in all fields.',
                'form_data': {'name': name, 'email': email, 'message': message},
            })

        send_mail(
            subject=f'Kyle Cup Contact: {name}',
            message=f'From: {name} <{email}>\n\n{message}',
            from_email='kylecup@mg.edwards.nz',
            recipient_list=['ben@edwards.nz'],
            fail_silently=False,
        )

        return render(request, 'support.html', {
            'months': models.Month.objects.all(),
            'success': True,
        })
    