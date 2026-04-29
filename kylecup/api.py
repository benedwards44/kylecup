from ninja import NinjaAPI
from ninja import ModelSchema
from leaderboard.models import Activity, AthleteMonthSummary
from typing import List
from leaderboard.strava import StravaClient
import decimal

class ActivitySchema(ModelSchema):

    display: str
    athlete_name: str
    pace_display: str
    distance_calculated: decimal.Decimal

    class Meta:
        model = Activity
        fields = [
            'id',
            'date',
            'distance',
            'pace'
        ]


class AthleteMonthSummarySchema(ModelSchema):
    athlete_name: str
    athlete_avatar: str
    total_distance: decimal.Decimal
    total_distance_raw: decimal.Decimal
    class Meta:
        model = AthleteMonthSummary
        fields = [
            'id',
        ]

api = NinjaAPI()


@api.get("/{month_slug}/activities", response=List[ActivitySchema])
def get_activities(request, month_slug):
    """
    Retrieve activities
    """
    client = StravaClient()
    client.sync_activities_if_stale(month_slug)
    return Activity.objects.filter(
        invalid=False, 
        athlete_month_summary__month__slug=month_slug
    )


@api.get("/{month_slug}/leaderboard", response=List[AthleteMonthSummarySchema])
def get_leaderboard(request, month_slug):
    """
    Retrieve leaderboard
    """
    return AthleteMonthSummary.objects.filter(month__slug=month_slug)


@api.post("/{month_slug}/sync")
def sync_activities(request, month_slug):
    """
    Sync activities for a given month. This is intended to be called manually when needed.
    """
    client = StravaClient()
    client.sync_activities(month_slug)
    return {"message": "Successfully ran Strava sync."}