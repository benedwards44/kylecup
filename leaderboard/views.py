from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from datetime import datetime


class IndexView(View):
    """
    Redirect straight to relevant month
    """
    def get(self, request, *args, **kwargs):
        return redirect('month', month=datetime.now().strftime("%b").lower())


class MonthView(TemplateView):
    """
    The month view
    """

    template_name = 'month.html'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super().get_context_data(**kwargs)
        # Add in a QuerySet of all the books
        context["title"] = datetime.strptime(self.kwargs['month'],'%b').strftime('%B')
        context["current_month"] = self.kwargs['month']
        return context

