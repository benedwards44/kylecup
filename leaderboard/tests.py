import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from leaderboard.email_backend import MailgunEmailBackend
from leaderboard.mailer import send_email
from leaderboard.models import (
    Activity,
    Athlete,
    AthleteMonthSummary,
    DeviceRegistration,
    Month,
)
from leaderboard.notifications import (
    _ordinal,
    notify_leaderboard_change,
    notify_new_activity,
    send_push_notification,
)
from leaderboard.strava import StravaClient
from leaderboard.utils import sort_leaderboard

# The whitenoise manifest storage requires collectstatic to have run, so use
# the plain storage when rendering templates in tests
TEST_STORAGES = {
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    }
}


def create_month(name='July', slug='jul', month_date=date(2026, 7, 1), **kwargs):
    return Month.objects.create(name=name, slug=slug, date=month_date, **kwargs)


def create_athlete(name='Kyle', slug='kyle', strava_id=1001, **kwargs):
    return Athlete.objects.create(name=name, slug=slug, strava_id=strava_id, **kwargs)


def create_activity(summary, strava_id=1, distance='10.00', pace='4.0000', activity_date=None, **kwargs):
    return Activity.objects.create(
        strava_id=strava_id,
        type=kwargs.pop('type', 'Run'),
        date=activity_date or timezone.now(),
        athlete_month_summary=summary,
        distance=Decimal(distance),
        pace=Decimal(pace),
        **kwargs,
    )


def fake_strava_activity(activity_id=555, activity_type='Run', start=None, distance=10500.0, speed=3.2):
    activity = mock.Mock()
    activity.id = activity_id
    activity.type = activity_type
    activity.start_date = start or timezone.now()
    activity.distance = distance
    activity.average_speed = speed
    return activity


class AthleteModelTests(TestCase):

    def test_str(self):
        self.assertEqual(str(create_athlete(name='Kyle')), 'Kyle')

    def test_avatar(self):
        self.assertEqual(create_athlete(slug='kyle').avatar(), '/static/images/avatars/kyle.png')


class MonthModelTests(TestCase):

    def test_str(self):
        self.assertEqual(str(create_month(name='July')), 'July')

    def test_ordered_by_date(self):
        aug = create_month(name='August', slug='aug', month_date=date(2026, 8, 1))
        jul = create_month(name='July', slug='jul', month_date=date(2026, 7, 1))
        self.assertEqual(list(Month.objects.all()), [jul, aug])


class AthleteMonthSummaryModelTests(TestCase):

    def setUp(self):
        self.month = create_month()
        self.athlete = create_athlete()
        self.summary = AthleteMonthSummary.objects.create(month=self.month, athlete=self.athlete)

    def test_str(self):
        self.assertEqual(str(self.summary), 'Kyle - July')

    def test_athlete_name(self):
        self.assertEqual(self.summary.athlete_name(), 'Kyle')

    def test_athlete_avatar_is_absolute(self):
        self.assertEqual(self.summary.athlete_avatar(), 'https://kylecup.edwards.nz/static/images/avatars/kyle.png')

    def test_total_distance_excludes_invalid(self):
        create_activity(self.summary, strava_id=1, distance='10.00')
        create_activity(self.summary, strava_id=2, distance='5.00', invalid=True)
        self.assertEqual(self.summary.total_distance(), Decimal('10.00'))
        self.assertEqual(self.summary.total_distance_raw(), Decimal('10.00'))

    def test_total_distance_applies_double_points(self):
        self.athlete.is_double_points = True
        self.athlete.save()
        self.month.is_double_points_month = True
        self.month.save()
        create_activity(self.summary, strava_id=1, distance='10.00')
        self.assertEqual(self.summary.total_distance(), Decimal('20.00'))
        self.assertEqual(self.summary.total_distance_raw(), Decimal('10.00'))


class ActivityModelTests(TestCase):

    def setUp(self):
        self.month = create_month()
        self.athlete = create_athlete()
        self.summary = AthleteMonthSummary.objects.create(month=self.month, athlete=self.athlete)

    def test_display(self):
        activity = create_activity(self.summary, distance='10.50', pace='4.0000')
        self.assertEqual(activity.display(), 'Kyle ran 10.50km at 4:10 min/km.')
        self.assertEqual(str(activity), activity.display())

    def test_display_shows_double_points_worth(self):
        self.athlete.is_double_points = True
        self.athlete.save()
        self.month.is_double_points_month = True
        self.month.save()
        activity = create_activity(self.summary, distance='10.00', pace='4.0000')
        self.assertIn('(worth 20.00km)', activity.display())

    def test_distance_calculated_requires_both_flags(self):
        activity = create_activity(self.summary, distance='10.00')

        self.assertEqual(activity.distance_calculated(), Decimal('10.00'))

        # Double points athlete in a normal month scores normally
        self.athlete.is_double_points = True
        self.athlete.save()
        self.assertEqual(activity.distance_calculated(), Decimal('10.00'))

        # Double points athlete in a double points month scores double
        self.month.is_double_points_month = True
        self.month.save()
        activity.refresh_from_db()
        self.assertEqual(activity.distance_calculated(), Decimal('20.00'))

    def test_type_display(self):
        self.assertEqual(create_activity(self.summary, strava_id=1, type='Run').type_display(), 'ran')
        self.assertEqual(create_activity(self.summary, strava_id=2, type='Walk').type_display(), 'walked')
        self.assertEqual(create_activity(self.summary, strava_id=3, type='Hike').type_display(), 'ran')

    def test_pace_display(self):
        # 4 m/s -> 250 seconds/km -> 4:10
        activity = create_activity(self.summary, pace='4.0000')
        self.assertEqual(activity.pace_display(), '4:10 min/km')

    def test_pace_display_rolls_over_seconds(self):
        # 299.9 seconds/km rounds to 60 seconds, which should roll into the minute
        activity = Activity(pace=Decimal('1000') / Decimal('299.9'))
        self.assertEqual(activity.pace_display(), '5:00 min/km')

    def test_pace_display_handles_no_pace(self):
        self.assertIsNone(Activity(pace=None).pace_display())

    def test_date_display(self):
        local_date = timezone.make_aware(datetime(2026, 7, 1, 9, 0))
        activity = create_activity(self.summary, activity_date=local_date)
        self.assertEqual(activity.date_display(), '1st Jul @ 9:00 AM')

    def test_suffix(self):
        activity = Activity()
        self.assertEqual(activity.suffix(1), 'st')
        self.assertEqual(activity.suffix(2), 'nd')
        self.assertEqual(activity.suffix(3), 'rd')
        self.assertEqual(activity.suffix(4), 'th')
        self.assertEqual(activity.suffix(11), 'th')
        self.assertEqual(activity.suffix(12), 'th')
        self.assertEqual(activity.suffix(13), 'th')
        self.assertEqual(activity.suffix(21), 'st')
        self.assertEqual(activity.suffix(22), 'nd')
        self.assertEqual(activity.suffix(23), 'rd')
        self.assertEqual(activity.suffix(30), 'th')
        self.assertEqual(activity.suffix(31), 'st')

    def test_ordered_most_recent_first(self):
        older = create_activity(self.summary, strava_id=1, activity_date=timezone.now() - timedelta(days=1))
        newer = create_activity(self.summary, strava_id=2, activity_date=timezone.now())
        self.assertEqual(list(Activity.objects.all()), [newer, older])


class DeviceRegistrationModelTests(TestCase):

    def test_str_truncates_token(self):
        registration = DeviceRegistration.objects.create(token='ExponentPushToken[abcdefghijklmnop]')
        self.assertEqual(str(registration), 'ExponentPushToken[ab...')


@mock.patch('leaderboard.utils.notify_leaderboard_change')
class SortLeaderboardTests(TestCase):

    def setUp(self):
        self.month = create_month()
        self.kyle = create_athlete(name='Kyle', slug='kyle', strava_id=1)
        self.ben = create_athlete(name='Ben', slug='ben', strava_id=2)
        self.kyle_summary = AthleteMonthSummary.objects.create(month=self.month, athlete=self.kyle)
        self.ben_summary = AthleteMonthSummary.objects.create(month=self.month, athlete=self.ben)

    def test_assigns_positions_by_distance(self, mock_notify):
        create_activity(self.kyle_summary, strava_id=1, distance='10.00')
        create_activity(self.ben_summary, strava_id=2, distance='20.00')

        leaderboard = sort_leaderboard('jul')

        self.assertEqual([entry.athlete.name for entry in leaderboard], ['Ben', 'Kyle'])
        self.ben_summary.refresh_from_db()
        self.kyle_summary.refresh_from_db()
        self.assertEqual(self.ben_summary.current_position, 1)
        self.assertEqual(self.kyle_summary.current_position, 2)
        mock_notify.assert_called_once_with([])

    def test_notifies_position_changes(self, mock_notify):
        self.kyle_summary.current_position = 1
        self.kyle_summary.save()
        self.ben_summary.current_position = 2
        self.ben_summary.save()

        # Ben overtakes Kyle
        create_activity(self.ben_summary, strava_id=1, distance='20.00')

        sort_leaderboard('jul')

        changes = mock_notify.call_args.args[0]
        self.assertIn(('Ben', 2, 1), changes)
        self.assertIn(('Kyle', 1, 2), changes)


class SendPushNotificationTests(TestCase):

    @mock.patch('leaderboard.notifications.PushClient')
    def test_does_nothing_without_registered_devices(self, mock_push_client):
        send_push_notification(title='Hi', body='There')
        mock_push_client.assert_not_called()

    @mock.patch('leaderboard.notifications.PushClient')
    def test_publishes_to_all_devices(self, mock_push_client):
        DeviceRegistration.objects.create(token='token-1')
        DeviceRegistration.objects.create(token='token-2')
        mock_push_client.return_value.publish_multiple.return_value = [mock.Mock(), mock.Mock()]

        send_push_notification(title='Hi', body='There')

        messages = mock_push_client.return_value.publish_multiple.call_args.args[0]
        self.assertEqual([message.to for message in messages], ['token-1', 'token-2'])
        self.assertEqual(messages[0].title, 'Hi')
        self.assertEqual(messages[0].body, 'There')

    @mock.patch('leaderboard.notifications.PushClient')
    def test_removes_unregistered_devices(self, mock_push_client):
        from exponent_server_sdk import DeviceNotRegisteredError

        DeviceRegistration.objects.create(token='dead-token')
        ticket = mock.Mock()
        ticket.validate_response.side_effect = DeviceNotRegisteredError(mock.Mock())
        mock_push_client.return_value.publish_multiple.return_value = [ticket]

        send_push_notification(title='Hi', body='There')

        self.assertFalse(DeviceRegistration.objects.filter(token='dead-token').exists())


@mock.patch('leaderboard.notifications.send_push_notification')
class NotifyNewActivityTests(TestCase):

    def setUp(self):
        self.month = create_month()
        self.kyle = create_athlete(name='Kyle', slug='kyle', strava_id=1)
        self.ben = create_athlete(name='Ben', slug='ben', strava_id=2)
        self.kyle_summary = AthleteMonthSummary.objects.create(month=self.month, athlete=self.kyle)
        self.ben_summary = AthleteMonthSummary.objects.create(month=self.month, athlete=self.ben)

    def test_leader_message_includes_gap_to_second(self, mock_send):
        create_activity(self.ben_summary, strava_id=1, distance='5.00')
        activity = create_activity(self.kyle_summary, strava_id=2, distance='10.00', pace='4.0000')

        notify_new_activity(activity)

        body = mock_send.call_args.kwargs['body']
        self.assertEqual(body, 'Kyle ran 10.00km at 4:10 min/km and is now 5.00km ahead of Ben in 1st place.')

    def test_chaser_message_includes_gap_to_athlete_above(self, mock_send):
        create_activity(self.ben_summary, strava_id=1, distance='20.00')
        activity = create_activity(self.kyle_summary, strava_id=2, distance='10.00', pace='4.0000')

        notify_new_activity(activity)

        body = mock_send.call_args.kwargs['body']
        self.assertEqual(body, 'Kyle ran 10.00km at 4:10 min/km and is now 10.00km behind Ben in 1st place.')

    def test_sole_athlete_message_has_no_comparison(self, mock_send):
        self.ben_summary.delete()
        activity = create_activity(self.kyle_summary, strava_id=1, distance='10.00', pace='4.0000')

        notify_new_activity(activity)

        body = mock_send.call_args.kwargs['body']
        self.assertEqual(body, 'Kyle ran 10.00km at 4:10 min/km.')


class NotifyLeaderboardChangeTests(TestCase):

    @mock.patch('leaderboard.notifications.send_push_notification')
    def test_does_nothing_without_changes(self, mock_send):
        notify_leaderboard_change([])
        mock_send.assert_not_called()

    @mock.patch('leaderboard.notifications.send_push_notification')
    def test_describes_moves_up_and_down(self, mock_send):
        notify_leaderboard_change([('Ben', 2, 1), ('Kyle', 1, 2)])
        body = mock_send.call_args.kwargs['body']
        self.assertEqual(body, 'Ben moved up to #1, Kyle dropped to #2')

    def test_ordinal(self):
        self.assertEqual(_ordinal(1), '1st')
        self.assertEqual(_ordinal(2), '2nd')
        self.assertEqual(_ordinal(3), '3rd')
        self.assertEqual(_ordinal(4), '4th')
        self.assertEqual(_ordinal(11), '11th')
        self.assertEqual(_ordinal(13), '13th')
        self.assertEqual(_ordinal(21), '21st')


class MailerTests(TestCase):

    def test_send_email_goes_to_admins(self):
        send_email(subject='Test subject', message='Test message')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Test subject')
        self.assertEqual(mail.outbox[0].to, ['ben@edwards.nz'])
        self.assertEqual(mail.outbox[0].from_email, 'kylecup@mg.edwards.nz')


@override_settings(MAILGUN_API_KEY='key-test', MAILGUN_DOMAIN='mg.test.com')
class MailgunEmailBackendTests(TestCase):

    def message(self, **kwargs):
        return EmailMessage(
            subject=kwargs.pop('subject', 'Subject'),
            body=kwargs.pop('body', 'Body'),
            from_email=kwargs.pop('from_email', 'sender@test.com'),
            to=kwargs.pop('to', ['to@test.com']),
            **kwargs,
        )

    @mock.patch('leaderboard.email_backend.requests.post')
    def test_posts_message_to_mailgun(self, mock_post):
        sent = MailgunEmailBackend().send_messages([
            self.message(cc=['cc@test.com'], bcc=['bcc@test.com']),
        ])

        self.assertEqual(sent, 1)
        url = mock_post.call_args.args[0]
        kwargs = mock_post.call_args.kwargs
        self.assertEqual(url, 'https://api.mailgun.net/v3/mg.test.com/messages')
        self.assertEqual(kwargs['auth'], ('api', 'key-test'))
        self.assertEqual(kwargs['data']['from'], 'sender@test.com')
        self.assertEqual(kwargs['data']['to'], ['to@test.com'])
        self.assertEqual(kwargs['data']['cc'], ['cc@test.com'])
        self.assertEqual(kwargs['data']['bcc'], ['bcc@test.com'])
        self.assertEqual(kwargs['data']['subject'], 'Subject')
        self.assertEqual(kwargs['data']['text'], 'Body')

    @mock.patch('leaderboard.email_backend.requests.post')
    def test_includes_html_alternative(self, mock_post):
        message = EmailMultiAlternatives('Subject', 'plain', 'sender@test.com', ['to@test.com'])
        message.attach_alternative('<b>html</b>', 'text/html')

        MailgunEmailBackend().send_messages([message])

        self.assertEqual(mock_post.call_args.kwargs['data']['html'], '<b>html</b>')

    @mock.patch('leaderboard.email_backend.requests.post')
    def test_skips_messages_without_recipients(self, mock_post):
        sent = MailgunEmailBackend().send_messages([self.message(to=[])])
        self.assertEqual(sent, 0)
        mock_post.assert_not_called()

    @mock.patch('leaderboard.email_backend.requests.post', side_effect=Exception('boom'))
    def test_raises_by_default(self, mock_post):
        with self.assertRaises(Exception):
            MailgunEmailBackend().send_messages([self.message()])

    @mock.patch('leaderboard.email_backend.requests.post', side_effect=Exception('boom'))
    def test_fail_silently_swallows_errors(self, mock_post):
        sent = MailgunEmailBackend(fail_silently=True).send_messages([self.message()])
        self.assertEqual(sent, 0)


@mock.patch('leaderboard.strava.sort_leaderboard')
@mock.patch('leaderboard.strava.notify_new_activity')
@mock.patch('leaderboard.strava.Client')
class ProcessWebhookEventTests(TestCase):

    def setUp(self):
        self.month = create_month()
        self.athlete = create_athlete(
            strava_id=53318588,
            strava_access_token='token',
            strava_refresh_token='refresh',
        )

    def strava_client(self, mock_client, activity):
        mock_client.return_value.refresh_access_token.return_value = {
            'access_token': 'new-token',
            'refresh_token': 'new-refresh',
        }
        mock_client.return_value.get_activity.return_value = activity
        return StravaClient()

    def test_creates_activity_and_summary(self, mock_client, mock_notify, mock_sort):
        start = timezone.make_aware(datetime(2026, 7, 5, 8, 30))
        client = self.strava_client(mock_client, fake_strava_activity(activity_id=555, start=start))

        client.process_webhook_event(555, 53318588)

        activity = Activity.objects.get(strava_id=555)
        self.assertEqual(activity.type, 'Run')
        self.assertEqual(activity.distance, Decimal('10.50'))
        self.assertEqual(activity.athlete_month_summary.athlete, self.athlete)
        self.assertEqual(activity.athlete_month_summary.month, self.month)
        mock_notify.assert_called_once_with(activity)
        mock_sort.assert_called_once_with('jul')

        # Tokens were refreshed and saved
        self.athlete.refresh_from_db()
        self.assertEqual(self.athlete.strava_access_token, 'new-token')

    def test_reuses_existing_summary(self, mock_client, mock_notify, mock_sort):
        summary = AthleteMonthSummary.objects.create(month=self.month, athlete=self.athlete)
        client = self.strava_client(mock_client, fake_strava_activity(activity_id=555))

        client.process_webhook_event(555, 53318588)

        self.assertEqual(AthleteMonthSummary.objects.count(), 1)
        self.assertEqual(Activity.objects.get(strava_id=555).athlete_month_summary, summary)

    def test_skips_duplicate_activity(self, mock_client, mock_notify, mock_sort):
        summary = AthleteMonthSummary.objects.create(month=self.month, athlete=self.athlete)
        create_activity(summary, strava_id=555)
        client = self.strava_client(mock_client, fake_strava_activity(activity_id=555))

        client.process_webhook_event(555, 53318588)

        self.assertEqual(Activity.objects.filter(strava_id=555).count(), 1)
        mock_notify.assert_not_called()

    def test_skips_non_run_activity(self, mock_client, mock_notify, mock_sort):
        client = self.strava_client(mock_client, fake_strava_activity(activity_type='Ride'))

        client.process_webhook_event(555, 53318588)

        self.assertEqual(Activity.objects.count(), 0)

    def test_skips_unknown_athlete(self, mock_client, mock_notify, mock_sort):
        client = self.strava_client(mock_client, fake_strava_activity())

        client.process_webhook_event(555, 99999)

        self.assertEqual(Activity.objects.count(), 0)
        mock_client.return_value.get_activity.assert_not_called()

    def test_skips_disconnected_athlete(self, mock_client, mock_notify, mock_sort):
        self.athlete.strava_connection_status = 'Disconnected'
        self.athlete.save()
        client = self.strava_client(mock_client, fake_strava_activity())

        client.process_webhook_event(555, 53318588)

        self.assertEqual(Activity.objects.count(), 0)

    def test_skips_activity_outside_known_months(self, mock_client, mock_notify, mock_sort):
        start = timezone.make_aware(datetime(2026, 9, 5, 8, 30))
        client = self.strava_client(mock_client, fake_strava_activity(start=start))

        client.process_webhook_event(555, 53318588)

        self.assertEqual(Activity.objects.count(), 0)


@mock.patch('leaderboard.strava.sort_leaderboard')
@mock.patch('leaderboard.strava.notify_new_activity')
@mock.patch('leaderboard.strava.Client')
class SyncActivitiesTests(TestCase):

    def setUp(self):
        self.month = create_month()
        self.athlete = create_athlete(
            strava_id=1001,
            strava_access_token='token',
            strava_refresh_token='refresh',
        )

    def strava_client(self, mock_client, activities):
        mock_client.return_value.refresh_access_token.return_value = {
            'access_token': 'new-token',
            'refresh_token': 'new-refresh',
        }
        mock_client.return_value.get_activities.return_value = activities
        return StravaClient()

    def test_creates_run_activities(self, mock_client, mock_notify, mock_sort):
        client = self.strava_client(mock_client, [
            fake_strava_activity(activity_id=1, activity_type='Run'),
            fake_strava_activity(activity_id=2, activity_type='Ride'),
        ])

        client.sync_activities('jul')

        self.assertEqual(Activity.objects.count(), 1)
        self.assertEqual(Activity.objects.get().strava_id, 1)
        self.assertEqual(mock_notify.call_count, 1)
        mock_sort.assert_called_once_with('jul')

        self.month.refresh_from_db()
        self.assertIsNotNone(self.month.last_sync_date)

    def test_skips_existing_activities(self, mock_client, mock_notify, mock_sort):
        summary = AthleteMonthSummary.objects.create(month=self.month, athlete=self.athlete)
        create_activity(summary, strava_id=1)
        client = self.strava_client(mock_client, [fake_strava_activity(activity_id=1)])

        client.sync_activities('jul')

        self.assertEqual(Activity.objects.filter(strava_id=1).count(), 1)
        mock_notify.assert_not_called()

    def test_skips_disconnected_athletes(self, mock_client, mock_notify, mock_sort):
        self.athlete.strava_connection_status = 'Disconnected'
        self.athlete.save()
        client = self.strava_client(mock_client, [fake_strava_activity()])

        client.sync_activities('jul')

        self.assertEqual(Activity.objects.count(), 0)
        mock_client.return_value.get_activities.assert_not_called()


class SyncActivitiesIfStaleTests(TestCase):

    def setUp(self):
        self.slug = timezone.now().strftime('%b').lower()
        self.month = create_month(slug=self.slug, month_date=timezone.now().date().replace(day=1))

    @override_settings(IS_LOCAL=False)
    @mock.patch.object(StravaClient, 'sync_activities')
    @mock.patch('leaderboard.strava.Client')
    def test_syncs_when_never_synced(self, mock_client, mock_sync):
        StravaClient().sync_activities_if_stale(self.slug)
        mock_sync.assert_called_once_with(self.slug)

    @override_settings(IS_LOCAL=False)
    @mock.patch.object(StravaClient, 'sync_activities')
    @mock.patch('leaderboard.strava.Client')
    def test_skips_when_recently_synced(self, mock_client, mock_sync):
        self.month.last_sync_date = timezone.now()
        self.month.save()
        StravaClient().sync_activities_if_stale(self.slug)
        mock_sync.assert_not_called()

    @override_settings(IS_LOCAL=False)
    @mock.patch.object(StravaClient, 'sync_activities')
    @mock.patch('leaderboard.strava.Client')
    def test_syncs_when_stale(self, mock_client, mock_sync):
        self.month.last_sync_date = timezone.now() - timedelta(hours=2)
        self.month.save()
        StravaClient().sync_activities_if_stale(self.slug)
        mock_sync.assert_called_once_with(self.slug)

    @override_settings(IS_LOCAL=True)
    @mock.patch.object(StravaClient, 'sync_activities')
    @mock.patch('leaderboard.strava.Client')
    def test_skips_when_local(self, mock_client, mock_sync):
        StravaClient().sync_activities_if_stale(self.slug)
        mock_sync.assert_not_called()


class StravaAuthTests(TestCase):

    @override_settings(IS_LOCAL=True, STRAVA_CLIENT_ID=123)
    @mock.patch('leaderboard.strava.Client')
    def test_get_auth_url(self, mock_client):
        mock_client.return_value.authorization_url.return_value = 'https://www.strava.com/oauth/authorize'

        url = StravaClient().get_auth_url()

        self.assertEqual(url, 'https://www.strava.com/oauth/authorize')
        kwargs = mock_client.return_value.authorization_url.call_args.kwargs
        self.assertEqual(kwargs['client_id'], 123)
        self.assertEqual(kwargs['redirect_uri'], 'http://example.com/strava/callback')

    @mock.patch('leaderboard.strava.Client')
    def test_auth_callback_saves_tokens(self, mock_client):
        athlete = create_athlete(strava_id=1001)
        mock_client.return_value.exchange_code_for_token.return_value = {
            'access_token': 'access',
            'refresh_token': 'refresh',
        }
        mock_client.return_value.get_athlete.return_value = mock.Mock(id=1001)

        StravaClient().auth_callback('auth-code')

        athlete.refresh_from_db()
        self.assertEqual(athlete.strava_access_token, 'access')
        self.assertEqual(athlete.strava_refresh_token, 'refresh')


class IndexViewTests(TestCase):

    def test_redirects_to_current_month(self):
        response = self.client.get(reverse('index'))
        self.assertRedirects(
            response,
            reverse('month', kwargs={'slug': timezone.now().strftime('%b').lower()}),
            fetch_redirect_response=False,
        )


@override_settings(STORAGES=TEST_STORAGES)
class MonthViewTests(TestCase):

    def setUp(self):
        self.month = create_month()
        self.athlete = create_athlete()
        self.summary = AthleteMonthSummary.objects.create(month=self.month, athlete=self.athlete)

    def test_renders_month(self):
        create_activity(self.summary, strava_id=1)
        create_activity(self.summary, strava_id=2, invalid=True)

        response = self.client.get(reverse('month', kwargs={'slug': 'jul'}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['activities']), 1)
        self.assertEqual(list(response.context['athletes']), [self.summary])
        self.assertEqual(list(response.context['months']), [self.month])

    def test_unknown_month_returns_404(self):
        response = self.client.get(reverse('month', kwargs={'slug': 'nope'}))
        self.assertEqual(response.status_code, 404)


@override_settings(STORAGES=TEST_STORAGES)
class PrivacyViewTests(TestCase):

    def test_renders(self):
        response = self.client.get(reverse('privacy'))
        self.assertEqual(response.status_code, 200)


@override_settings(STORAGES=TEST_STORAGES)
class SupportViewTests(TestCase):

    def test_renders(self):
        response = self.client.get(reverse('support'))
        self.assertEqual(response.status_code, 200)

    def test_valid_submission_emails_admins(self):
        response = self.client.post(reverse('support'), {
            'name': 'Kyle',
            'email': 'kyle@example.com',
            'message': 'Help!',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['success'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Kyle Cup Contact: Kyle')
        self.assertIn('kyle@example.com', mail.outbox[0].body)

    def test_missing_fields_shows_error(self):
        response = self.client.post(reverse('support'), {'name': 'Kyle'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('error', response.context)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(STORAGES=TEST_STORAGES)
class NotifyViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='admin', password='password')

    def test_requires_login(self):
        response = self.client.get(reverse('notify'))
        self.assertEqual(response.status_code, 302)

    def test_renders_when_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('notify'))
        self.assertEqual(response.status_code, 200)

    @mock.patch('leaderboard.views.send_push_notification')
    def test_valid_submission_sends_notification(self, mock_send):
        self.client.force_login(self.user)
        response = self.client.post(reverse('notify'), {'title': 'Hello', 'message': 'World'})

        self.assertTrue(response.context['success'])
        mock_send.assert_called_once_with(title='Hello', body='World')

    @mock.patch('leaderboard.views.send_push_notification')
    def test_missing_fields_shows_error(self, mock_send):
        self.client.force_login(self.user)
        response = self.client.post(reverse('notify'), {'title': 'Hello'})

        self.assertIn('error', response.context)
        mock_send.assert_not_called()


class StravaViewTests(TestCase):

    @mock.patch('leaderboard.views.StravaClient')
    def test_connect_redirects_to_strava(self, mock_client):
        mock_client.return_value.get_auth_url.return_value = 'https://www.strava.com/oauth/authorize'

        response = self.client.get(reverse('strava_connect'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://www.strava.com/oauth/authorize')

    @mock.patch('leaderboard.views.StravaClient')
    def test_callback_exchanges_code(self, mock_client):
        response = self.client.get(reverse('strava_callback'), {'code': 'auth-code'})

        mock_client.return_value.auth_callback.assert_called_once_with('auth-code')
        self.assertRedirects(response, reverse('index'), fetch_redirect_response=False)

    @mock.patch('leaderboard.views.StravaClient')
    def test_sync_triggers_sync_and_redirects(self, mock_client):
        response = self.client.get(reverse('strava_sync', kwargs={'month': 'jul'}))

        mock_client.return_value.sync_activities.assert_called_once_with('jul')
        self.assertRedirects(
            response,
            reverse('month', kwargs={'slug': 'jul'}),
            fetch_redirect_response=False,
        )


class StravaWebhookViewTests(TestCase):

    def webhook_payload(self, **overrides):
        payload = {
            'aspect_type': 'create',
            'event_time': 1783310967,
            'object_id': 19196504020,
            'object_type': 'activity',
            'owner_id': 53318588,
            'subscription_id': 359704,
            'updates': {},
        }
        payload.update(overrides)
        return payload

    def post_webhook(self, payload):
        return self.client.post(
            reverse('strava_webhook'),
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_get_echoes_challenge(self):
        response = self.client.get(reverse('strava_webhook'), {'hub.challenge': 'abc123'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'hub.challenge': 'abc123'})

    def test_get_without_challenge_returns_400(self):
        response = self.client.get(reverse('strava_webhook'))
        self.assertEqual(response.status_code, 400)

    @mock.patch('leaderboard.views.StravaClient')
    def test_activity_create_event_is_processed(self, mock_client):
        response = self.post_webhook(self.webhook_payload())

        self.assertEqual(response.status_code, 200)
        mock_client.return_value.process_webhook_event.assert_called_once_with(19196504020, 53318588)
        self.assertEqual(len(mail.outbox), 0)

    @mock.patch('leaderboard.views.StravaClient')
    def test_other_events_are_ignored(self, mock_client):
        for payload in [
            self.webhook_payload(aspect_type='update'),
            self.webhook_payload(aspect_type='delete'),
            self.webhook_payload(object_type='athlete'),
        ]:
            response = self.post_webhook(payload)
            self.assertEqual(response.status_code, 200)

        mock_client.return_value.process_webhook_event.assert_not_called()

    @mock.patch('leaderboard.views.StravaClient')
    def test_processing_errors_still_return_200(self, mock_client):
        mock_client.return_value.process_webhook_event.side_effect = Exception('boom')

        response = self.post_webhook(self.webhook_payload())

        self.assertEqual(response.status_code, 200)

    @mock.patch('leaderboard.views.StravaClient')
    def test_processing_errors_email_admins(self, mock_client):
        mock_client.return_value.process_webhook_event.side_effect = Exception('boom')

        self.post_webhook(self.webhook_payload())

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Kyle Cup: Strava webhook processing failed')
        self.assertEqual(mail.outbox[0].to, ['ben@edwards.nz'])
        self.assertIn('19196504020', mail.outbox[0].body)
        self.assertIn('boom', mail.outbox[0].body)

    @mock.patch('leaderboard.views.send_email', side_effect=Exception('mail down'))
    @mock.patch('leaderboard.views.StravaClient')
    def test_still_returns_200_when_failure_email_fails(self, mock_client, mock_send):
        mock_client.return_value.process_webhook_event.side_effect = Exception('boom')

        response = self.post_webhook(self.webhook_payload())

        self.assertEqual(response.status_code, 200)


class ApiTests(TestCase):

    def setUp(self):
        self.month = create_month()
        self.athlete = create_athlete()
        self.summary = AthleteMonthSummary.objects.create(month=self.month, athlete=self.athlete)

    def test_get_activities_excludes_invalid(self):
        create_activity(self.summary, strava_id=1, distance='10.50', pace='4.0000')
        create_activity(self.summary, strava_id=2, invalid=True)

        response = self.client.get('/api/jul/activities')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['athlete_name'], 'Kyle')
        self.assertEqual(data[0]['pace_display'], '4:10 min/km')

    def test_get_leaderboard(self):
        create_activity(self.summary, strava_id=1, distance='10.00')

        response = self.client.get('/api/jul/leaderboard')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['athlete_name'], 'Kyle')
        self.assertEqual(Decimal(str(data[0]['total_distance'])), Decimal('10.00'))

    @mock.patch('kylecup.api.StravaClient')
    def test_sync_endpoint_triggers_sync(self, mock_client):
        response = self.client.post('/api/jul/sync')

        self.assertEqual(response.status_code, 200)
        mock_client.return_value.sync_activities.assert_called_once_with('jul')

    def test_register_push_token_is_idempotent(self):
        for _ in range(2):
            response = self.client.post(
                '/api/push-token/register',
                data=json.dumps({'token': 'ExponentPushToken[abc]'}),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 200)

        self.assertEqual(DeviceRegistration.objects.count(), 1)
