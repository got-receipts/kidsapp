import json
from datetime import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from pywebpush import WebPushException, webpush

from rewards.models import Profile, PushSubscription, ReminderDispatch


class Command(BaseCommand):
    help = "Send the daily guardian reminder to issue behavior stars after 7:30 PM Eastern."

    def handle(self, *args, **options):
        now = timezone.localtime()
        today = now.date()
        if now.time() < time(19, 30):
            self.stdout.write("Not yet 7:30 PM in the configured timezone; no reminder sent.")
            return
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
        if not settings.VAPID_PUBLIC_KEY or not settings.VAPID_PRIVATE_KEY:
            self.stderr.write("VAPID keys are not configured; cannot send push reminders.")
            return
        payload = json.dumps(
            {
                "title": "Good behavior stars",
                "body": "It is 7:30 PM. Add today's star for: " + ", ".join(missing_stars) + ".",
                "url": "/",
            }
        )
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
        ReminderDispatch.objects.create(day=today, recipient_count=sent)
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} behavior-star reminder notification(s)."))
