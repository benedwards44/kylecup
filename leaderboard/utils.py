from leaderboard.models import AthleteMonthSummary

def sort_leaderboard(month_slug):
    """
    Sort the leaderboard by current position, then by total distance.
    """

    summary = AthleteMonthSummary.objects.filter(month__slug=month_slug)
    leaderboard = sorted(summary, key=lambda athlete: athlete.total_distance(), reverse=True)

    for l in leaderboard:
        l.current_position = leaderboard.index(l) + 1
        l.save()

    return leaderboard