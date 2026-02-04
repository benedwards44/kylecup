from django.shortcuts import redirect
from django.views import View
from django.views.generic.detail import DetailView
from . import models
from datetime import datetime


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
        context["athletes"] = models.AthleteMonthSummary.objects.filter(month=self.get_object())
        return context

