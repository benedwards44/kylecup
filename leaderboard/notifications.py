import logging

from exponent_server_sdk import (
    DeviceNotRegisteredError,
    PushClient,
    PushMessage,
    PushServerError,
    PushTicketError,
)

from leaderboard.models import DeviceRegistration

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
    send_push_notification(
        title='New Activity',
        body=activity.display(),
        data={'type': 'activity', 'activity_id': activity.id},
    )


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
