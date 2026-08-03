from django.db import models
from decimal import *
from django.utils import timezone


class Athlete(models.Model):
    """
    Holds details about an athlete
    """

    name = models.CharField(max_length=80)
    slug = models.SlugField()
    is_double_points = models.BooleanField(default=False)
    strava_id = models.PositiveIntegerField(blank=True, null=True)
    strava_access_token = models.CharField(max_length=255, blank=True, null=True)
    strava_refresh_token = models.CharField(max_length=255, blank=True, null=True)
    strava_connection_status = models.CharField(choices=[
        ('Connected', 'Connected'),
        ('Disconnected', 'Disconnected'),
    ], default='Connected')

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
    is_double_points_month = models.BooleanField(default=False)
    last_sync_date = models.DateTimeField(blank=True, null=True)

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
    current_position = models.PositiveIntegerField(blank=True, null=True)
    points = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text='Points awarded for the final placing once the month has finished'
    )

    class Meta:
        ordering = ['current_position', 'month__date']

    def __str__(self):
        return self.athlete.name + ' - ' + self.month.name
    
    def athlete_name(self):
        return self.athlete.name
    
    def athlete_avatar(self):
        return 'https://kylecup.edwards.nz' + self.athlete.avatar()

    def total_distance(self):
        total = Decimal(0)
        for activity in self.activities.filter(invalid=False):
            total = total + activity.distance_calculated() 
        return total
    
    def total_distance_raw(self):
        total = Decimal(0)
        for activity in self.activities.filter(invalid=False):
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
    invalid = models.BooleanField(
        default=False, 
        help_text='Used to manually invalidate an activity if it\'s deemed to be outside the spirit of the game'
    )

    class Meta:
        verbose_name_plural = "activities"
        ordering = ['-date']

    def __str__(self):
        return self.display()
    
    def display(self):
        return '%s ran %skm%sat %s.' % (
            self.athlete_month_summary.athlete.name, 
            str(self.distance), 
            (' (worth ' + str(self.distance_calculated()) + 'km) ')  if self.athlete_month_summary.athlete.is_double_points else ' ',
            str(self.pace_display()),
        )
    
    def athlete_name(self):
        return self.athlete_month_summary.athlete.name
    
    def distance_calculated(self):
        if self.athlete_month_summary.athlete.is_double_points and self.athlete_month_summary.month.is_double_points_month:
            return self.distance * 2
        return self.distance
    
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
        if day in (11, 12, 13):
            return 'th'
        return {1:'st',2:'nd',3:'rd'}.get(day%10, 'th')


class DeviceRegistration(models.Model):
    token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.token[:20] + '...'


class WebhookEvent(models.Model):
    """
    Log the Strava webhooks
    """
    created_date = models.DateTimeField(auto_now_add=True)
    data = models.TextField()
    status = models.CharField(max_length=20, default='New', choices=[
        ('New', 'New'),
        ('Processed', 'Processed'),
        ('Error', 'Error')
    ])
    error_message = models.TextField(blank=True, null=True)