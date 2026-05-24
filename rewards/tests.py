from datetime import date, datetime, timezone as datetime_timezone
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import BehaviorStar, Chore, LedgerRequest, Profile, Wallet
from .services import ensure_today_chores


class LedgerApprovalTests(TestCase):
    def setUp(self):
        child_user = User.objects.create_user(username="kj", password="test")
        guardian_user = User.objects.create_user(username="dad", password="test")
        self.child = Profile.objects.create(user=child_user, display_name="KJ", role=Profile.Role.CHILD)
        self.guardian = Profile.objects.create(user=guardian_user, display_name="Dad", role=Profile.Role.GUARDIAN)
        self.wallet = Wallet.objects.create(child=self.child, tokens=20, cash_cents=500)

    def test_approval_updates_shared_wallet_and_completes_chore(self):
        chore = Chore.objects.create(child=self.child, title="Dishes", token_reward=8, cash_reward_cents=50)
        request = LedgerRequest.objects.create(
            child=self.child,
            requested_by=self.child,
            kind=LedgerRequest.Kind.CHORE,
            description="Completed chore: Dishes",
            token_delta=8,
            cash_delta_cents=50,
            chore=chore,
        )

        request.approve(self.guardian)

        self.wallet.refresh_from_db()
        chore.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 28)
        self.assertEqual(self.wallet.cash_cents, 550)
        self.assertEqual(chore.status, Chore.Status.COMPLETED)

    def test_purchase_cannot_be_approved_without_sufficient_tokens(self):
        request = LedgerRequest.objects.create(
            child=self.child,
            requested_by=self.child,
            kind=LedgerRequest.Kind.STORE,
            description="Store request: Big reward",
            token_delta=-25,
        )

        with self.assertRaises(ValidationError):
            request.approve(self.guardian)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 20)

    def test_decline_after_approval_does_not_reverse_the_approved_balance(self):
        request = LedgerRequest.objects.create(
            child=self.child,
            requested_by=self.child,
            kind=LedgerRequest.Kind.GOAL,
            description="Reached goal",
            token_delta=10,
        )
        request.approve(self.guardian)
        request.decline(self.guardian)

        self.wallet.refresh_from_db()
        request.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 30)
        self.assertEqual(request.status, LedgerRequest.Status.APPROVED)

    def test_late_chore_completion_does_not_create_token_request(self):
        chore = Chore.objects.create(
            child=self.child,
            title="Clean your room",
            token_reward=4,
            due_date=date(2026, 5, 24),
        )
        self.client.force_login(self.child.user)
        late = datetime(2026, 5, 24, 19, 1, tzinfo=datetime_timezone.utc)

        with patch("rewards.views.timezone.localtime", return_value=late):
            self.client.post(reverse("submit_chore", args=[chore.pk]))

        chore.refresh_from_db()
        self.assertEqual(chore.status, Chore.Status.LATE)
        self.assertFalse(LedgerRequest.objects.filter(chore=chore).exists())

    def test_guardian_star_awards_two_tokens_only_once_per_day(self):
        self.client.force_login(self.guardian.user)
        star_data = {"child_id": self.child.pk, "day": "2026-05-24"}

        self.client.post(reverse("award_star"), star_data)
        self.client.post(reverse("award_star"), star_data)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 22)
        self.assertEqual(BehaviorStar.objects.filter(child=self.child).count(), 1)


class DailyChoreRotationTests(TestCase):
    def setUp(self):
        for name in ("KJ", "Astoria", "Saphira"):
            user = User.objects.create_user(username=name.lower(), password="test")
            profile = Profile.objects.create(user=user, display_name=name, role=Profile.Role.CHILD)
            Wallet.objects.create(child=profile)

    @patch("rewards.services.timezone.localdate", return_value=date(2026, 5, 24))
    def test_twelve_daily_chores_are_divided_evenly(self, mocked_date):
        ensure_today_chores()

        self.assertEqual(Chore.objects.filter(due_date=date(2026, 5, 24)).count(), 12)
        for child in Profile.objects.filter(role=Profile.Role.CHILD):
            self.assertEqual(child.chores.filter(due_date=date(2026, 5, 24)).count(), 4)
