from datetime import date, datetime, time, timedelta, timezone as datetime_timezone
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import BehaviorStar, ChildRule, Chore, DailyScheduleEvent, FamilySettings, HouseRule, LedgerRequest, Profile, SavingsGoal, Wallet
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
        self.assertContains(response, "removed since your last check-in")

    def test_guardian_sees_review_popup_for_submitted_chore(self):
        chore = Chore.objects.create(child=self.child, title="Make your bed", token_reward=4, status=Chore.Status.SUBMITTED)
        LedgerRequest.objects.create(
            child=self.child,
            requested_by=self.child,
            kind=LedgerRequest.Kind.CHORE,
            description="Completed chore: Make your bed",
            token_delta=4,
            chore=chore,
        )
        self.client.force_login(self.guardian.user)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Quest verification")
        self.assertContains(response, "Review +4 t")
        self.assertContains(response, "Approve Completed")
        self.assertContains(response, "Deny Chore")

    def test_guardian_actions_use_popup_interfaces(self):
        self.client.force_login(self.guardian.user)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Guardian Actions")
        self.assertContains(response, 'data-open-dialog="action-deduct"')
        self.assertContains(response, "Take Points")
        self.assertContains(response, "data-confirm-deduction")
        self.assertContains(response, 'data-open-dialog="action-chore"')

    def test_optional_make_bed_quest_cannot_earn_credit_after_ten_am(self):
        chore = Chore.objects.create(
            child=self.child,
            title="Make your bed",
            token_reward=4,
            optional=True,
            due_date=date(2026, 5, 24),
            credit_deadline=time(10, 0),
        )
        self.client.force_login(self.child.user)
        after_cutoff = datetime(2026, 5, 24, 10, 1, tzinfo=datetime_timezone.utc)

        with patch("rewards.views.timezone.localtime", return_value=after_cutoff):
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

    def test_child_can_request_savings_move_but_only_dad_can_approve_it(self):
        self.client.force_login(self.child.user)
        self.client.post(reverse("request_spending_transfer"), {"cash_amount": "2.00"})
        entry = LedgerRequest.objects.get(kind=LedgerRequest.Kind.TRANSFER)

        gg_user = User.objects.create_user(username="gg", password="test")
        Profile.objects.create(user=gg_user, display_name="GG", role=Profile.Role.GUARDIAN)
        self.client.force_login(gg_user)
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
        gg_user = User.objects.create_user(username="gg", password="test")
        Profile.objects.create(user=gg_user, display_name="GG", role=Profile.Role.GUARDIAN)
        self.client.force_login(gg_user)

        self.client.post(reverse("review_request", args=[entry.pk, "approve"]))

        self.wallet.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 20)
        self.assertEqual(self.wallet.cash_cents, 500)
        self.assertEqual(entry.status, LedgerRequest.Status.PENDING)

    def test_child_wallet_page_has_money_forms_and_guardian_is_redirected(self):
        sibling_user = User.objects.create_user(username="astoria", password="test")
        sibling = Profile.objects.create(user=sibling_user, display_name="Astoria", role=Profile.Role.CHILD)
        Wallet.objects.create(child=sibling)
        self.client.force_login(self.child.user)
        response = self.client.get(reverse("wallet_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tokens &amp; Money")
        self.assertContains(response, "data-money-pad")
        self.assertContains(response, "Pay Family")
        self.assertContains(response, "Savings to Tokens")
        self.assertContains(response, "Tokens to Savings")
        self.assertContains(response, "Astoria")

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

    def test_child_can_request_tokens_to_savings_conversion(self):
        self.client.force_login(self.child.user)

        response = self.client.post(reverse("request_tokens_to_savings"), {"cash_amount": "1.00"})

        entry = LedgerRequest.objects.get(kind=LedgerRequest.Kind.CONVERT)
        self.assertRedirects(response, reverse("wallet_page"))
        self.assertEqual(entry.token_delta, -10)
        self.assertEqual(entry.cash_delta_cents, 100)
        self.assertEqual(entry.status, LedgerRequest.Status.PENDING)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 20)
        self.assertEqual(self.wallet.cash_cents, 500)

    def test_child_cannot_request_tokens_to_savings_above_token_balance(self):
        self.client.force_login(self.child.user)

        self.client.post(reverse("request_tokens_to_savings"), {"cash_amount": "3.00"})

        self.assertFalse(LedgerRequest.objects.filter(kind=LedgerRequest.Kind.CONVERT).exists())

    def test_child_can_send_spending_to_another_child_with_history_for_both(self):
        sibling_user = User.objects.create_user(username="astoria", password="test")
        sibling = Profile.objects.create(user=sibling_user, display_name="Astoria", role=Profile.Role.CHILD)
        sibling_wallet = Wallet.objects.create(child=sibling)
        self.wallet.spending_cents = 500
        self.wallet.save(update_fields=["spending_cents"])
        self.client.force_login(self.child.user)

        response = self.client.post(
            reverse("send_family_transfer"),
            {"recipient_id": sibling.pk, "cash_amount": "2.25"},
        )

        self.assertRedirects(response, reverse("wallet_page"))
        self.wallet.refresh_from_db()
        sibling_wallet.refresh_from_db()
        self.assertEqual(self.wallet.spending_cents, 275)
        self.assertEqual(sibling_wallet.spending_cents, 225)
        sent = LedgerRequest.objects.get(child=self.child, kind=LedgerRequest.Kind.GIFT)
        received = LedgerRequest.objects.get(child=sibling, kind=LedgerRequest.Kind.GIFT)
        self.assertEqual(sent.spending_delta_cents, -225)
        self.assertEqual(sent.counterparty, sibling)
        self.assertEqual(received.spending_delta_cents, 225)
        self.assertEqual(received.counterparty, self.child)
        self.assertEqual(sent.status, LedgerRequest.Status.APPROVED)

    def test_child_cannot_send_more_than_available_spending(self):
        sibling_user = User.objects.create_user(username="astoria", password="test")
        sibling = Profile.objects.create(user=sibling_user, display_name="Astoria", role=Profile.Role.CHILD)
        sibling_wallet = Wallet.objects.create(child=sibling)
        self.client.force_login(self.child.user)

        self.client.post(reverse("send_family_transfer"), {"recipient_id": sibling.pk, "cash_amount": "1.00"})

        self.wallet.refresh_from_db()
        sibling_wallet.refresh_from_db()
        self.assertEqual(self.wallet.spending_cents, 0)
        self.assertEqual(sibling_wallet.spending_cents, 0)
        self.assertFalse(LedgerRequest.objects.filter(kind=LedgerRequest.Kind.GIFT).exists())

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

    @override_settings(GOOGLE_CALENDAR_ID="family@group.calendar.google.com", GOOGLE_CALENDAR_API_KEY="test-key")
    def test_public_google_calendar_events_appear_on_child_daily_plan(self):
        cache.clear()
        payload = (
            b'{"items":[{"summary":"Dance practice","location":"Community center",'
            b'"start":{"date":"2026-05-24"}}]}'
        )
        self.client.force_login(self.child.user)

        with patch("rewards.services.urlopen", return_value=BytesIO(payload)):
            with patch("rewards.services.timezone.localdate", return_value=date(2026, 5, 24)):
                response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Family Google Calendar")
        self.assertContains(response, "Dance practice")
        self.assertContains(response, "Community center")

    def test_guardian_can_hide_a_personal_rule(self):
        rule = ChildRule.objects.create(child=self.child, title="Temporary reminder")
        self.client.force_login(self.guardian.user)

        self.client.post(reverse("guardian_remove", args=["child_rule", rule.pk]))

        rule.refresh_from_db()
        self.assertFalse(rule.active)

    def test_grounded_mode_hides_child_wallet_and_verifies_chores_without_rewards(self):
        chore = Chore.objects.create(child=self.child, title="Put away backpack", token_reward=4)
        self.client.force_login(self.guardian.user)
        self.client.post(
            reverse("guardian_lockdown"),
            {"child_id": self.child.pk, "action": "lock", "reason": "Focus on chores today."},
        )
        self.child.refresh_from_db()
        self.assertTrue(self.child.grounded)

        self.client.force_login(self.child.user)
        dashboard = self.client.get(reverse("dashboard"))
        self.assertContains(dashboard, "Balances locked")
        self.assertNotContains(dashboard, reverse("wallet_page"))
        self.assertRedirects(self.client.get(reverse("wallet_page")), reverse("dashboard"))
        self.client.post(reverse("submit_chore", args=[chore.pk]))
        entry = LedgerRequest.objects.get(chore=chore)
        self.assertEqual(entry.token_delta, 0)

        self.client.force_login(self.guardian.user)
        self.client.post(reverse("review_request", args=[entry.pk, "approve"]))
        self.wallet.refresh_from_db()
        chore.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 20)
        self.assertEqual(chore.status, Chore.Status.COMPLETED)

    def test_grounded_mode_blocks_rewards_and_money_changes_until_unlocked(self):
        self.child.grounded = True
        self.child.save(update_fields=["grounded"])
        entry = LedgerRequest.objects.create(
            child=self.child,
            requested_by=self.child,
            kind=LedgerRequest.Kind.CONVERT,
            description="Frozen conversion",
            token_delta=10,
            cash_delta_cents=-100,
        )
        self.client.force_login(self.guardian.user)

        self.client.post(reverse("review_request", args=[entry.pk, "approve"]))
        self.client.post(reverse("award_star"), {"child_id": self.child.pk, "day": timezone.localdate().isoformat()})

        entry.refresh_from_db()
        self.wallet.refresh_from_db()
        self.assertEqual(entry.status, LedgerRequest.Status.PENDING)
        self.assertEqual(self.wallet.tokens, 20)
        self.assertFalse(BehaviorStar.objects.filter(child=self.child).exists())

    def test_gg_can_remove_behavior_tokens_and_token_balance_may_go_negative(self):
        gg_user = User.objects.create_user(username="gg", password="test")
        gg = Profile.objects.create(user=gg_user, display_name="GG", role=Profile.Role.GUARDIAN)
        self.client.force_login(gg.user)

        response = self.client.post(
            reverse("guardian_behavior_deduction"),
            {"child_id": self.child.pk, "reason": "Unkind words", "tokens": "25"},
        )

        self.assertRedirects(response, f"/?child={self.child.pk}")
        self.wallet.refresh_from_db()
        entry = LedgerRequest.objects.get(kind=LedgerRequest.Kind.BEHAVIOR)
        self.assertEqual(self.wallet.tokens, -5)
        self.assertEqual(entry.token_delta, -25)
        self.assertEqual(entry.status, LedgerRequest.Status.APPROVED)
        self.assertEqual(entry.reviewed_by, gg)

    def test_behavior_deduction_is_blocked_during_grounded_mode(self):
        self.child.grounded = True
        self.child.save(update_fields=["grounded"])
        self.client.force_login(self.guardian.user)

        self.client.post(
            reverse("guardian_behavior_deduction"),
            {"child_id": self.child.pk, "reason": "Test deduction", "tokens": "3"},
        )

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 20)
        self.assertFalse(LedgerRequest.objects.filter(kind=LedgerRequest.Kind.BEHAVIOR).exists())

    def test_only_dad_can_save_google_calendar_settings(self):
        self.client.force_login(self.guardian.user)
        self.client.post(
            reverse("dad_google_calendar_settings"),
            {"child_id": self.child.pk, "google_calendar_enabled": "on", "google_calendar_id": "family@group.calendar.google.com"},
        )
        settings_record = FamilySettings.objects.get()
        self.assertTrue(settings_record.google_calendar_enabled)
        self.assertEqual(settings_record.google_calendar_id, "family@group.calendar.google.com")

        mom_user = User.objects.create_user(username="mom", password="test")
        mom = Profile.objects.create(user=mom_user, display_name="Mom", role=Profile.Role.VIEWER)
        self.client.force_login(mom.user)
        self.client.post(
            reverse("dad_google_calendar_settings"),
            {"child_id": self.child.pk, "google_calendar_enabled": "on", "google_calendar_id": "changed@calendar.google.com"},
        )
        settings_record.refresh_from_db()
        self.assertEqual(settings_record.google_calendar_id, "family@group.calendar.google.com")

    def test_mom_viewer_sees_progress_without_controls_or_balances(self):
        mom_user = User.objects.create_user(username="mom", password="test")
        mom = Profile.objects.create(user=mom_user, display_name="Mom", role=Profile.Role.VIEWER)
        Chore.objects.create(child=self.child, title="Clean your room", status=Chore.Status.COMPLETED, due_date=timezone.localdate())
        self.client.force_login(mom.user)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Family Viewer")
        self.assertContains(response, "School grades")
        self.assertContains(response, "Today's chores")
        self.assertContains(response, "Behavior star calendar")
        self.assertContains(response, "Growth goals")
        self.assertNotContains(response, "Take Points")
        self.assertNotContains(response, "savings")
        self.assertNotContains(response, "Activate Grounded Mode")
        self.assertNotContains(response, "Approve Completed")
        self.assertNotContains(response, "Add grade")
        self.assertNotContains(response, "Add award")

    def test_mom_viewer_cannot_post_guardian_changes(self):
        mom_user = User.objects.create_user(username="mom", password="test")
        mom = Profile.objects.create(user=mom_user, display_name="Mom", role=Profile.Role.VIEWER)
        chore = Chore.objects.create(child=self.child, title="Read together", due_date=timezone.localdate())
        self.client.force_login(mom.user)

        self.client.post(reverse("guardian_lockdown"), {"child_id": self.child.pk, "action": "lock"})
        self.client.post(
            reverse("guardian_create", args=["grade"]),
            {"child_id": self.child.pk, "subject": "Math", "assignment": "Quiz", "score": "95", "maximum_score": "100"},
        )
        self.client.post(reverse("award_star"), {"child_id": self.child.pk, "day": timezone.localdate().isoformat()})
        self.client.post(reverse("guardian_behavior_deduction"), {"child_id": self.child.pk, "reason": "No", "tokens": "4"})
        self.client.post(reverse("start_chore", args=[chore.pk]))

        self.child.refresh_from_db()
        chore.refresh_from_db()
        self.assertFalse(self.child.grounded)
        self.assertFalse(self.child.grades.exists())
        self.assertFalse(BehaviorStar.objects.filter(child=self.child).exists())
        self.assertFalse(LedgerRequest.objects.filter(kind=LedgerRequest.Kind.BEHAVIOR).exists())
        self.assertEqual(chore.status, Chore.Status.OPEN)
        self.assertRedirects(self.client.get(reverse("wallet_page")), reverse("dashboard"))

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

        self.assertEqual(Chore.objects.filter(due_date=date(2026, 5, 24)).count(), 15)
        for child in Profile.objects.filter(role=Profile.Role.CHILD):
            self.assertEqual(child.chores.filter(due_date=date(2026, 5, 24), optional=False).count(), 4)
            bonus = child.chores.get(due_date=date(2026, 5, 24), optional=True)
            self.assertEqual(bonus.title, "Make your bed")
            self.assertEqual(bonus.credit_deadline, time(10, 0))
