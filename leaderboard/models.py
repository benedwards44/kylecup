from django.db import models
from decimal import *


class Athlete(models.Model):
    """
    Holds details about an athlete
    """

    name = models.CharField(max_length=80)
    slug = models.SlugField()
    strava_id = models.PositiveIntegerField(blank=True, null=True)
    strava_access_token = models.CharField(max_length=255, blank=True, null=True)
    strava_refresh_token = models.CharField(max_length=255, blank=True, null=True)

    icon_colour = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return self.name
    
    def avatar(self):
        return '/static/images/avatars/%s.png' % self.slug


class Month(models.Model):
    """
    Holds details about a month
    """
    
    name = models.CharField(max_length=80)
    slug = models.SlugField()
    date = models.DateField()

    class Meta:
        ordering = ['date']

    def __str__(self):
        return self.name


class AthleteMonthSummary(models.Model):
    """
    Summary and totals for an athlete for a given month
    """

    month = models.ForeignKey(Month, on_delete=models.CASCADE)
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE)

    class Meta:
        ordering = ['month__date']

    def __str__(self):
        return self.athlete.name + ' - ' + self.month.name

    def total_distance(self):
        total = Decimal(0)
        for activity in self.activities.all():
            total = total + activity.distance 
        return total


class Activity(models.Model):
    """
    Holds detail for a given activty
    """

    strava_id = models.BigIntegerField()
    type = models.CharField(max_length=40)
    date = models.DateTimeField()
    athlete_month_summary = models.ForeignKey(AthleteMonthSummary, on_delete=models.CASCADE, related_name='activities')
    distance = models.DecimalField(max_digits=6, decimal_places=2)
    pace = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        verbose_name_plural = "activities"
        ordering = ['date']

    def __str__(self):
        return '%s ran %skm at %s per km' % (self.athlete_month_summary.athlete.name, str(self.distance), str(self.pace))
    
    def type_display(self):
        if self.type == 'Run':
            return 'ran'
        elif self.type == 'Walk':
            return 'walked'
        return 'ran'
