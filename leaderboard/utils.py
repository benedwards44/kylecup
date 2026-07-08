import calendar
from datetime import date

from django.conf import settings
from django.utils import timezone

from leaderboard.models import AthleteMonthSummary, Month
from leaderboard.notifications import notify_leaderboard_change

def sort_leaderboard(month_slug):
    """
    Sort the leaderboard by current position, then by total distance.
    """

    summary = AthleteMonthSummary.objects.filter(month__slug=month_slug)
    leaderboard = sorted(summary, key=lambda athlete: athlete.total_distance(), reverse=True)

    changes = []
    for i, entry in enumerate(leaderboard):
        new_position = i + 1
        if entry.current_position and entry.current_position != new_position:
            changes.append((entry.athlete.name, entry.current_position, new_position))
        entry.current_position = new_position
        entry.save()

    notify_leaderboard_change(changes)

    return leaderboard


def month_has_finished(month):
    """
    True once the last day of the month has passed.
    """
    last_day = calendar.monthrange(month.date.year, month.date.month)[1]
    return timezone.localdate() > date(month.date.year, month.date.month, last_day)


def award_points():
    """
    Award placing points for any finished month that hasn't been scored yet.
    """
    for month in Month.objects.all():
        if not month_has_finished(month):
            continue
        for summary in AthleteMonthSummary.objects.filter(month=month, points__isnull=True):
            summary.points = settings.PLACING_POINTS.get(summary.current_position, 0)
            summary.save()
