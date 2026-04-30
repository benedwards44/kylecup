import logging

from exponent_server_sdk import (
    DeviceNotRegisteredError,
    PushClient,
    PushMessage,
    PushServerError,
    PushTicketError,
)

from leaderboard.models import AthleteMonthSummary, DeviceRegistration

logger = logging.getLogger(__name__)


def send_push_notification(title, body, data=None):
    tokens = list(DeviceRegistration.objects.values_list('token', flat=True))
    if not tokens:
        return

    messages = [
        PushMessage(to=token, title=title, body=body, data=data or {})
        for token in tokens
    ]

    try:
        client = PushClient()
        responses = client.publish_multiple(messages)
    except PushServerError:
        logger.exception('Push server error')
        return

    for i, response in enumerate(responses):
        try:
            response.validate_response()
        except DeviceNotRegisteredError:
            DeviceRegistration.objects.filter(token=tokens[i]).delete()
        except PushTicketError:
            logger.warning('Push ticket error for token %s', tokens[i])


def notify_new_activity(activity):
    summary = activity.athlete_month_summary
    month = summary.month
    name = summary.athlete.name
    distance = activity.distance
    pace = activity.pace_display()

    ranked = sorted(
        AthleteMonthSummary.objects.filter(month=month),
        key=lambda s: s.total_distance(),
        reverse=True,
    )

    position = next(
        (i + 1 for i, s in enumerate(ranked) if s.id == summary.id),
        None,
    )

    body = f'{name} ran {distance}km at {pace}'

    if position and position > 1:
        above = ranked[position - 2]
        gap = above.total_distance() - summary.total_distance()
        ordinal = _ordinal(position - 1)
        body += f' and is now {gap:.2f}km behind {above.athlete.name} in {ordinal} place.'
    elif position == 1 and len(ranked) > 1:
        below = ranked[1]
        gap = summary.total_distance() - below.total_distance()
        body += f' and is now {gap:.2f}km ahead of {below.athlete.name} in 1st place.'
    else:
        body += '.'

    send_push_notification(
        title='New Activity',
        body=body,
        data={'type': 'activity', 'activity_id': activity.id},
    )


def _ordinal(n):
    if 11 <= (n % 100) <= 13:
        return f'{n}th'
    return f'{n}{["th", "st", "nd", "rd"][min(n % 10, 4)] if n % 10 < 4 else "th"}'


def notify_leaderboard_change(changes):
    if not changes:
        return

    lines = []
    for name, old_pos, new_pos in changes:
        if new_pos < old_pos:
            lines.append(f'{name} moved up to #{new_pos}')
        else:
            lines.append(f'{name} dropped to #{new_pos}')

    send_push_notification(
        title='Leaderboard Update',
        body=', '.join(lines),
        data={'type': 'leaderboard'},
    )
