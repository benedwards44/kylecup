from leaderboard.models import AthleteMonthSummary
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
