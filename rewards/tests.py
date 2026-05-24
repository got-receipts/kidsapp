from datetime import date, datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import BehaviorStar, ChildRule, Chore, DailyScheduleEvent, HouseRule, LedgerRequest, Profile, SavingsGoal, Wallet
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

    def test_unverified_checked_chore_records_penalty_and_allows_token_debt(self):
        chore = Chore.objects.create(child=self.child, title="Put away toys", token_reward=25)
        entry = LedgerRequest.objects.create(
            child=self.child,
            requested_by=self.child,
            kind=LedgerRequest.Kind.CHORE,
            description="Completed chore: Put away toys",
            token_delta=25,
            chore=chore,
        )
        self.client.force_login(self.guardian.user)

        self.client.post(reverse("review_request", args=[entry.pk, "decline"]))

        self.wallet.refresh_from_db()
        chore.refresh_from_db()
        entry.refresh_from_db()
        penalty = LedgerRequest.objects.get(kind=LedgerRequest.Kind.PENALTY)
        self.assertEqual(entry.status, LedgerRequest.Status.DECLINED)
        self.assertEqual(chore.status, Chore.Status.NOT_VERIFIED)
        self.assertEqual(penalty.token_delta, -25)
        self.assertEqual(penalty.status, LedgerRequest.Status.APPROVED)
        self.assertEqual(self.wallet.tokens, -5)

        self.child.last_recap_at = timezone.now() - timedelta(days=1)
        self.child.last_recap_day = timezone.localdate() - timedelta(days=1)
        self.child.save(update_fields=["last_recap_at", "last_recap_day"])
        self.client.force_login(self.child.user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["recap_token_loss"], 25)
        self.assertContains(response, "removed because a checked quest was not verified")

    def test_guardian_star_awards_two_tokens_only_once_per_day(self):
        self.client.force_login(self.guardian.user)
        star_data = {"child_id": self.child.pk, "day": "2026-05-24"}

        self.client.post(reverse("award_star"), star_data)
        self.client.post(reverse("award_star"), star_data)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 22)
        self.assertEqual(BehaviorStar.objects.filter(child=self.child).count(), 1)

    def test_child_can_request_savings_move_but_only_dad_can_approve_it(self):
        self.client.force_login(self.child.user)
        self.client.post(reverse("request_spending_transfer"), {"cash_amount": "2.00"})
        entry = LedgerRequest.objects.get(kind=LedgerRequest.Kind.TRANSFER)

        mom_user = User.objects.create_user(username="mom", password="test")
        Profile.objects.create(user=mom_user, display_name="Mom", role=Profile.Role.GUARDIAN)
        self.client.force_login(mom_user)
        self.client.post(reverse("review_request", args=[entry.pk, "approve"]))
        entry.refresh_from_db()
        self.assertEqual(entry.status, LedgerRequest.Status.PENDING)

        self.client.force_login(self.guardian.user)
        self.client.post(reverse("review_request", args=[entry.pk, "approve"]))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.cash_cents, 300)
        self.assertEqual(self.wallet.spending_cents, 200)

    def test_dad_balance_correction_is_approved_and_audited(self):
        self.client.force_login(self.guardian.user)
        self.client.post(
            reverse("dad_balance_adjustment"),
            {
                "child_id": self.child.pk,
                "account": "spending",
                "direction": "add",
                "cash_amount": "4.25",
                "reason": "Allowance loaded",
            },
        )

        self.wallet.refresh_from_db()
        entry = LedgerRequest.objects.get(kind=LedgerRequest.Kind.BALANCE)
        self.assertEqual(self.wallet.spending_cents, 425)
        self.assertEqual(entry.status, LedgerRequest.Status.APPROVED)

    def test_non_dad_guardian_cannot_approve_savings_to_token_conversion(self):
        entry = LedgerRequest.objects.create(
            child=self.child,
            requested_by=self.child,
            kind=LedgerRequest.Kind.CONVERT,
            description="Convert savings to tokens",
            token_delta=20,
            cash_delta_cents=-200,
        )
        mom_user = User.objects.create_user(username="mom", password="test")
        Profile.objects.create(user=mom_user, display_name="Mom", role=Profile.Role.GUARDIAN)
        self.client.force_login(mom_user)

        self.client.post(reverse("review_request", args=[entry.pk, "approve"]))

        self.wallet.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 20)
        self.assertEqual(self.wallet.cash_cents, 500)
        self.assertEqual(entry.status, LedgerRequest.Status.PENDING)

    def test_child_wallet_page_has_money_forms_and_guardian_is_redirected(self):
        self.client.force_login(self.child.user)
        response = self.client.get(reverse("wallet_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tokens &amp; Money")
        self.assertContains(response, "Custom Savings amount")

        self.client.force_login(self.guardian.user)
        response = self.client.get(reverse("wallet_page"))
        self.assertRedirects(response, reverse("dashboard"))

    def test_preset_conversion_creates_pending_ten_token_request(self):
        self.client.force_login(self.child.user)

        response = self.client.post(reverse("request_conversion"), {"cash_amount": "1.00"})

        entry = LedgerRequest.objects.get(kind=LedgerRequest.Kind.CONVERT)
        self.assertRedirects(response, reverse("wallet_page"))
        self.assertEqual(entry.token_delta, 10)
        self.assertEqual(entry.cash_delta_cents, -100)
        self.assertEqual(entry.status, LedgerRequest.Status.PENDING)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 20)
        self.assertEqual(self.wallet.cash_cents, 500)

    def test_daily_recap_shows_new_star_and_is_dismissed_for_today(self):
        self.child.last_recap_at = timezone.now() - timedelta(days=1)
        self.child.last_recap_day = timezone.localdate() - timedelta(days=1)
        self.child.save(update_fields=["last_recap_at", "last_recap_day"])
        star = BehaviorStar.objects.create(child=self.child, awarded_by=self.guardian, day=timezone.localdate())
        entry = LedgerRequest.objects.create(
            child=self.child,
            requested_by=self.guardian,
            kind=LedgerRequest.Kind.STAR,
            description="Good behavior star",
            token_delta=2,
            behavior_star=star,
        )
        entry.approve(self.guardian)
        self.client.force_login(self.child.user)

        response = self.client.get(reverse("dashboard"))
        self.assertTrue(response.context["show_recap"])
        self.assertEqual(response.context["recap_star_count"], 1)

        self.client.post(reverse("dismiss_recap"))
        self.child.refresh_from_db()
        self.assertEqual(self.child.last_recap_day, timezone.localdate())

    def test_child_quest_progress_separates_submitted_from_verified(self):
        Chore.objects.create(child=self.child, title="Submitted", status=Chore.Status.SUBMITTED, due_date=timezone.localdate())
        Chore.objects.create(child=self.child, title="Verified", status=Chore.Status.COMPLETED, due_date=timezone.localdate())
        self.client.force_login(self.child.user)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.context["chore_completed"], 2)
        self.assertEqual(response.context["chore_verified"], 1)
        self.assertContains(response, "guardian verified")
        self.assertContains(response, "data-quest-deadline")

    def test_guardian_daily_plan_and_rules_appear_in_child_morning_message(self):
        self.client.force_login(self.guardian.user)
        today = timezone.localdate().isoformat()

        self.client.post(
            reverse("guardian_create", args=["schedule"]),
            {"child_id": self.child.pk, "day": today, "start_time": "09:30", "title": "Library visit", "details": "Bring your book bag."},
        )
        self.client.post(
            reverse("guardian_create", args=["child_rule"]),
            {"child_id": self.child.pk, "title": "Pack homework", "details": "Check the blue folder."},
        )
        self.client.post(
            reverse("guardian_create", args=["house_rule"]),
            {"child_id": self.child.pk, "title": "Kind voices", "details": "Speak respectfully."},
        )

        self.assertTrue(DailyScheduleEvent.objects.filter(child=self.child, title="Library visit").exists())
        self.assertTrue(ChildRule.objects.filter(child=self.child, title="Pack homework").exists())
        self.assertTrue(HouseRule.objects.filter(title="Kind voices").exists())

        self.client.force_login(self.child.user)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Today's Plan")
        self.assertContains(response, "Library visit")
        self.assertContains(response, "Pack homework")
        self.assertContains(response, "Kind voices")

    def test_guardian_can_hide_a_personal_rule(self):
        rule = ChildRule.objects.create(child=self.child, title="Temporary reminder")
        self.client.force_login(self.guardian.user)

        self.client.post(reverse("guardian_remove", args=["child_rule", rule.pk]))

        rule.refresh_from_db()
        self.assertFalse(rule.active)

    def test_child_can_create_savings_goal_and_progress_uses_savings_balance(self):
        self.client.force_login(self.child.user)

        self.client.post(reverse("save_savings_goal"), {"name": "New scooter", "target_amount": "10.00"})

        goal = SavingsGoal.objects.get(child=self.child)
        self.assertEqual(goal.target_cents, 1000)
        self.assertEqual(goal.saved_cents, 500)
        self.assertEqual(goal.percent, 50)

    def test_guardian_cannot_create_goal_on_child_savings_profile(self):
        self.client.force_login(self.guardian.user)

        self.client.post(reverse("save_savings_goal"), {"name": "Changed", "target_amount": "1.00"})

        self.assertFalse(SavingsGoal.objects.filter(child=self.child).exists())


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
