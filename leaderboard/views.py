from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic.detail import DetailView
from leaderboard.mailer import send_email
from leaderboard.notifications import send_push_notification
from leaderboard.models import DeviceRegistration
from . import models
from django.utils import timezone
from leaderboard.strava import StravaClient
from leaderboard.utils import award_points, month_has_finished
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
import traceback


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
        context["months"] = models.Month.objects.all()
        context["activities"] = models.Activity.objects.filter(invalid=False, athlete_month_summary__month=self.get_object())
        context["athletes"] = models.AthleteMonthSummary.objects.filter(month=self.get_object())
        return context

class LeaderboardView(View):
    """
    The season leaderboard, showing points scored for each month's placing
    """

    def get(self, request):
        # Score any finished months that haven't been scored yet
        award_points()

        months = models.Month.objects.all()
        scored_months = [month for month in months if month_has_finished(month)]

        summaries = {
            (summary.athlete_id, summary.month_id): summary
            for summary in models.AthleteMonthSummary.objects.filter(month__in=scored_months)
        }

        rows = []
        for athlete in models.Athlete.objects.all():
            monthly = []
            for month in scored_months:
                summary = summaries.get((athlete.id, month.id))
                monthly.append(summary.points if summary else None)
            rows.append({
                'athlete': athlete,
                'monthly': monthly,
                'total': sum(points for points in monthly if points),
            })
        rows.sort(key=lambda row: row['total'], reverse=True)

        return render(request, 'leaderboard.html', {
            'months': months,
            'scored_months': scored_months,
            'rows': rows,
        })


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

@method_decorator(csrf_exempt, name='dispatch')
class StravaWebhookView(View):
    """
    Handle webhook from Strava for activities
    """
    
    def get(self, request, *args, **kwargs):
        challenge = request.GET.get('hub.challenge') 
        if challenge:
            return JsonResponse({
                'hub.challenge': challenge,
            }, status=200)
        else:
            return JsonResponse({
                'message': 'No hub.challenge parameter found in query parameters',
            }, status=400)
        
    def post(self, request, *args, **kwargs):
        data = json.loads(request.body)
        models.Log.objects.create(data=json.dumps(data, indent=4))
        if data.get('aspect_type') == 'create' and data.get('object_type') == 'activity':
            try:
                client = StravaClient()
                client.process_webhook_event(data.get('object_id'), data.get('owner_id'))
            except Exception:
                # Always return a 200 so Strava doesn't keep retrying
                try:
                    send_email(
                        subject='Kyle Cup: Strava webhook processing failed',
                        message='Failed to process webhook:\n\n%s\n\n%s' % (
                            json.dumps(data, indent=4),
                            traceback.format_exc(),
                        ),
                    )
                except Exception:
                    pass

        return JsonResponse({
            'message': 'Message processed.',
        }, status=200)


class PrivacyView(View):
    def get(self, request):
        return render(request, 'privacy.html', {
            'months': models.Month.objects.all(),
            'today': timezone.now().date(),
        })


class NotifyView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'notify.html', {
            'months': models.Month.objects.all(),
        })

    def post(self, request):
        title = request.POST.get('title', '').strip()
        message = request.POST.get('message', '').strip()

        if not all([title, message]):
            return render(request, 'notify.html', {
                'months': models.Month.objects.all(),
                'error': 'Please fill in all fields.',
                'form_data': {'title': title, 'message': message},
            })

        device_count = DeviceRegistration.objects.count()
        send_push_notification(title=title, body=message)

        return render(request, 'notify.html', {
            'months': models.Month.objects.all(),
            'success': True,
            'device_count': device_count,
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

        send_email(
            subject=f'Kyle Cup Contact: {name}',
            message=f'From: {name} <{email}>\n\n{message}'
        )

        return render(request, 'support.html', {
            'months': models.Month.objects.all(),
            'success': True,
        })
    