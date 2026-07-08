from ninja import NinjaAPI, Schema
from ninja import ModelSchema
from leaderboard.models import Activity, AthleteMonthSummary, DeviceRegistration
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
            'points'
        ]

class PushTokenSchema(Schema):
    token: str

api = NinjaAPI()


@api.get("/{month_slug}/activities", response=List[ActivitySchema])
def get_activities(request, month_slug):
    """
    Retrieve activities
    """
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


@api.get("/leaderboard", response=List[AthleteMonthSummarySchema])
def get_leaderboard_full(request):
    """
    Retrieve leaderboard
    """
    return AthleteMonthSummary.objects.filter(points__isnull=False).order_by('month__date')


@api.post("/{month_slug}/sync")
def sync_activities(request, month_slug):
    """
    Sync activities for a given month. This is intended to be called manually when needed.
    """
    client = StravaClient()
    client.sync_activities(month_slug)
    return {"message": "Successfully ran Strava sync."}


@api.post("/push-token/register")
def register_push_token(request, payload: PushTokenSchema):
    DeviceRegistration.objects.get_or_create(token=payload.token)
    return {"message": "Token registered."}