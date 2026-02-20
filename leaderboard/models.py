from django.db import models
from decimal import *
from django.utils import timezone


class Athlete(models.Model):
    """
    Holds details about an athlete
    """

    name = models.CharField(max_length=80)
    slug = models.SlugField()
    strava_id = models.PositiveIntegerField(blank=True, null=True)
    strava_access_token = models.CharField(max_length=255, blank=True, null=True)
    strava_refresh_token = models.CharField(max_length=255, blank=True, null=True)

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
    pace = models.DecimalField(max_digits=6, decimal_places=4)

    class Meta:
        verbose_name_plural = "activities"
        ordering = ['-date']

    def __str__(self):
        return '%s ran %skm at %s per km' % (self.athlete_month_summary.athlete.name, str(self.distance), str(self.pace))
    
    def type_display(self):
        if self.type == 'Run':
            return 'ran'
        elif self.type == 'Walk':
            return 'walked'
        return 'ran'
    
    def pace_display(self):
        if self.pace:
            seconds_per_km = 1000 / self.pace
            minutes = int(seconds_per_km // 60)
            seconds = int(round(seconds_per_km % 60))
            if seconds == 60:
                minutes += 1
                seconds = 0
            return f"{minutes}:{seconds:02d} min/km"
    
    def date_display(self):
        date_converted = timezone.localtime(self.date)
        return date_converted.strftime('%-d') + self.suffix(date_converted.day) + date_converted.strftime(' %b @ %-I:%M %p')
    
    def suffix(self, day):
        return {1:'st',2:'nd',3:'rd'}.get(day%20, 'th')
