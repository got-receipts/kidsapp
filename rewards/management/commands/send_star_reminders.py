import json
from datetime import time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from pywebpush import WebPushException, webpush

from rewards.models import DailyScheduleEvent, Profile, PushSubscription, ReminderDispatch, ScheduleReminderDispatch


class Command(BaseCommand):
    help = "Send guardian push reminders for behavior stars and tomorrow's schedule."

    def handle(self, *args, **options):
        now = timezone.localtime()
        today = now.date()
        performed = False
        if now.time() >= time(19, 30):
            performed = True
            self._send_star_reminder(today)
        if now.time() >= time(21, 0):
            performed = True
            self._send_schedule_reminder(today)
        if not performed:
            self.stdout.write("Not yet 7:30 PM in the configured timezone; no reminder sent.")

    def _send_star_reminder(self, today):
        if ReminderDispatch.objects.filter(day=today).exists():
            self.stdout.write("Today's behavior-star reminder has already been sent.")
            return
        missing_stars = list(
            Profile.objects.filter(role=Profile.Role.CHILD)
            .exclude(behavior_stars__day=today)
            .values_list("display_name", flat=True)
        )
        if not missing_stars:
            ReminderDispatch.objects.create(day=today, recipient_count=0)
            self.stdout.write("Every child already has today's star recorded.")
            return
        sent = self._send_push(
            "Good behavior stars",
            "It is 7:30 PM. Add today's star for: " + ", ".join(missing_stars) + ".",
        )
        if sent is None:
            return
        ReminderDispatch.objects.create(day=today, recipient_count=sent)
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} behavior-star reminder notification(s)."))

    def _send_schedule_reminder(self, today):
        if ScheduleReminderDispatch.objects.filter(day=today).exists():
            self.stdout.write("Today's schedule-planning reminder has already been sent.")
            return
        tomorrow = today + timedelta(days=1)
        children_waiting = list(
            Profile.objects.filter(role=Profile.Role.CHILD)
            .exclude(
                pk__in=DailyScheduleEvent.objects.filter(day=tomorrow, approved_at__isnull=False).values("child_id")
            )
            .values_list("display_name", flat=True)
        )
        if not children_waiting:
            ScheduleReminderDispatch.objects.create(day=today, recipient_count=0)
            self.stdout.write("Every child already has tomorrow's approved schedule.")
            return
        sent = self._send_push(
            "Tomorrow's family schedule",
            "It is 9:00 PM. Create or approve tomorrow's plan for: " + ", ".join(children_waiting) + ".",
        )
        if sent is None:
            return
        ScheduleReminderDispatch.objects.create(day=today, recipient_count=sent)
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} schedule-planning reminder notification(s)."))

    def _send_push(self, title, body):
        if not settings.VAPID_PUBLIC_KEY or not settings.VAPID_PRIVATE_KEY:
            self.stderr.write("VAPID keys are not configured; cannot send push reminders.")
            return None
        payload = json.dumps({"title": title, "body": body, "url": "/"})
        sent = 0
        for subscription in PushSubscription.objects.filter(active=True, guardian__role=Profile.Role.GUARDIAN):
            try:
                webpush(
                    subscription_info={
                        "endpoint": subscription.endpoint,
                        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                    },
                    data=payload,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": settings.VAPID_CLAIMS_EMAIL},
                )
                sent += 1
            except WebPushException as error:
                if error.response is not None and error.response.status_code in (404, 410):
                    subscription.active = False
                    subscription.save(update_fields=["active"])
                self.stderr.write(f"Push delivery failed for one subscription: {error}")
        return sent
