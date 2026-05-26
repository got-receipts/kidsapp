from datetime import date, datetime, time, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    AuditLog,
    BehaviorNote,
    BehaviorStar,
    ChildRule,
    Chore,
    CommunicationSchedule,
    DailyScheduleEvent,
    FamilySettings,
    FamilyMessage,
    FamilyCall,
    HouseRule,
    LedgerRequest,
    Notification,
    Profile,
    Purchase,
    RuleAcknowledgement,
    SavingsGoal,
    ShoppingCartItem,
    ShoppingOrder,
    ShoppingProduct,
    StoreItem,
    Wallet,
)
from .services import ensure_today_chores


class LedgerApprovalTests(TestCase):
    def setUp(self):
        child_user = User.objects.create_user(username="kj", password="test")
        guardian_user = User.objects.create_user(username="dad", password="test")
        self.child = Profile.objects.create(user=child_user, display_name="KJ", role=Profile.Role.CHILD)
        self.guardian = Profile.objects.create(user=guardian_user, display_name="Dad", role=Profile.Role.GUARDIAN)
        self.wallet = Wallet.objects.create(child=self.child, tokens=20, cash_cents=500)

    def test_chore_approval_awards_tokens_only_and_completes_chore(self):
        chore = Chore.objects.create(child=self.child, title="Dishes", token_reward=8)
        request = LedgerRequest.objects.create(
            child=self.child,
            requested_by=self.child,
            kind=LedgerRequest.Kind.CHORE,
            description="Completed chore: Dishes",
            token_delta=8,
            chore=chore,
        )

        request.approve(self.guardian)

        self.wallet.refresh_from_db()
        chore.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 28)
        self.assertEqual(self.wallet.cash_cents, 500)
        self.assertEqual(chore.status, Chore.Status.COMPLETED)

    def test_chore_approval_rejects_any_cash_delta(self):
        chore = Chore.objects.create(child=self.child, title="Dishes", token_reward=8)
        request = LedgerRequest.objects.create(
            child=self.child,
            requested_by=self.child,
            kind=LedgerRequest.Kind.CHORE,
            description="Invalid cash chore",
            token_delta=8,
            cash_delta_cents=50,
            chore=chore,
        )

        with self.assertRaises(ValidationError):
            request.approve(self.guardian)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.cash_cents, 500)

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

    def test_legacy_move_to_spending_is_not_needed_in_cash_app_flow(self):
        self.client.force_login(self.child.user)
        response = self.client.post(reverse("request_spending_transfer"), {"cash_amount": "2.00"}, follow=True)

        self.wallet.refresh_from_db()
        self.assertContains(response, "already available to send or spend")
        self.assertEqual(self.wallet.cash_cents, 500)
        self.assertEqual(self.wallet.spending_cents, 0)
        self.assertFalse(LedgerRequest.objects.filter(kind=LedgerRequest.Kind.TRANSFER).exists())

    def test_parent_cash_app_balance_correction_is_approved_and_audited(self):
        self.client.force_login(self.guardian.user)
        self.client.post(
            reverse("dad_balance_adjustment"),
            {
                "child_id": self.child.pk,
                "account": "savings",
                "direction": "add",
                "cash_amount": "4.25",
                "reason": "Allowance loaded",
            },
        )

        self.wallet.refresh_from_db()
        entry = LedgerRequest.objects.get(kind=LedgerRequest.Kind.BALANCE)
        self.assertEqual(self.wallet.cash_cents, 925)
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
        self.assertContains(response, "Cash App")
        self.assertContains(response, "Family Cash")
        self.assertContains(response, "Convert Tokens")
        self.assertContains(response, "Send Tokens")
        self.assertContains(response, "Send Money")
        self.assertContains(response, "Spend Money")
        self.assertContains(response, "Money stays money")
        self.assertContains(response, "Astoria")
        self.assertContains(response, "Home")
        self.assertContains(response, "data-money-pad")

        self.client.force_login(self.guardian.user)
        response = self.client.get(reverse("wallet_page"))
        self.assertRedirects(response, reverse("dashboard"))

    def test_token_to_cash_conversion_is_immediate_and_cash_cannot_convert_back(self):
        self.client.force_login(self.child.user)

        response = self.client.post(reverse("request_token_cashout"), {"tokens": "10"})

        entry = LedgerRequest.objects.get(kind=LedgerRequest.Kind.CASH_OUT)
        self.assertRedirects(response, reverse("wallet_page"))
        self.assertEqual(entry.token_delta, -10)
        self.assertEqual(entry.cash_delta_cents, 100)
        self.assertEqual(entry.status, LedgerRequest.Status.APPROVED)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 10)
        self.assertEqual(self.wallet.cash_cents, 600)

        self.client.post(reverse("request_conversion"), {"cash_amount": "1.00"})
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 10)
        self.assertEqual(self.wallet.cash_cents, 600)
        self.assertFalse(LedgerRequest.objects.filter(kind=LedgerRequest.Kind.CONVERT).exists())

    def test_child_can_send_tokens_directly_to_sibling(self):
        sibling_user = User.objects.create_user(username="astoria", password="test")
        sibling = Profile.objects.create(user=sibling_user, display_name="Astoria", role=Profile.Role.CHILD)
        sibling_wallet = Wallet.objects.create(child=sibling)
        self.client.force_login(self.child.user)

        response = self.client.post(reverse("send_token_gift"), {"recipient_id": sibling.pk, "tokens": "5"})

        self.assertRedirects(response, reverse("wallet_page"))
        self.wallet.refresh_from_db()
        sibling_wallet.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 15)
        self.assertEqual(sibling_wallet.tokens, 5)
        self.assertEqual(LedgerRequest.objects.filter(kind=LedgerRequest.Kind.GIFT).count(), 2)

    def test_child_cannot_convert_more_tokens_than_available(self):
        self.client.force_login(self.child.user)

        self.client.post(reverse("request_token_cashout"), {"tokens": "30"})

        self.assertFalse(LedgerRequest.objects.filter(kind=LedgerRequest.Kind.CASH_OUT).exists())

    def test_parent_rate_controls_immediate_token_conversion(self):
        FamilySettings.objects.create(pk=1, tokens_per_dollar=20, updated_by=self.guardian)
        self.client.force_login(self.child.user)

        self.client.post(reverse("request_token_cashout"), {"tokens": "20"})

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 0)
        self.assertEqual(self.wallet.cash_cents, 600)
        self.assertTrue(Notification.objects.filter(recipient=self.child, kind=Notification.Kind.WALLET).exists())
        self.assertTrue(AuditLog.objects.filter(action="token_cashout_completed").exists())

    def test_converted_cash_can_be_sent_and_spent_from_cash_app_immediately(self):
        sibling_user = User.objects.create_user(username="astoria", password="test")
        sibling = Profile.objects.create(user=sibling_user, display_name="Astoria", role=Profile.Role.CHILD)
        sibling_wallet = Wallet.objects.create(child=sibling)
        self.wallet.cash_cents = 0
        self.wallet.save(update_fields=["cash_cents"])
        self.client.force_login(self.child.user)

        self.client.post(reverse("request_token_cashout"), {"tokens": "20"})
        self.client.post(reverse("send_family_transfer"), {"recipient_id": sibling.pk, "cash_amount": "0.75"})
        self.client.post(reverse("request_store_spend"), {"cash_amount": "1.00"})

        self.wallet.refresh_from_db()
        sibling_wallet.refresh_from_db()
        spend = LedgerRequest.objects.get(child=self.child, kind=LedgerRequest.Kind.SPEND)
        self.assertEqual(self.wallet.tokens, 0)
        self.assertEqual(self.wallet.cash_cents, 25)
        self.assertEqual(sibling_wallet.cash_cents, 75)
        self.assertEqual(spend.cash_delta_cents, -100)
        self.assertEqual(spend.status, LedgerRequest.Status.PENDING)

    def test_child_can_send_cash_to_another_child_with_history_for_both(self):
        sibling_user = User.objects.create_user(username="astoria", password="test")
        sibling = Profile.objects.create(user=sibling_user, display_name="Astoria", role=Profile.Role.CHILD)
        sibling_wallet = Wallet.objects.create(child=sibling)
        self.client.force_login(self.child.user)

        response = self.client.post(
            reverse("send_family_transfer"),
            {"recipient_id": sibling.pk, "cash_amount": "2.25"},
        )

        self.assertRedirects(response, reverse("wallet_page"))
        self.wallet.refresh_from_db()
        sibling_wallet.refresh_from_db()
        self.assertEqual(self.wallet.cash_cents, 275)
        self.assertEqual(sibling_wallet.cash_cents, 225)
        sent = LedgerRequest.objects.get(child=self.child, kind=LedgerRequest.Kind.GIFT)
        received = LedgerRequest.objects.get(child=sibling, kind=LedgerRequest.Kind.GIFT)
        self.assertEqual(sent.cash_delta_cents, -225)
        self.assertEqual(sent.counterparty, sibling)
        self.assertEqual(received.cash_delta_cents, 225)
        self.assertEqual(received.counterparty, self.child)
        self.assertEqual(sent.status, LedgerRequest.Status.APPROVED)

    def test_wallet_transfer_returns_to_wallet_with_confirmation_marker(self):
        sibling_user = User.objects.create_user(username="astoria", password="test")
        sibling = Profile.objects.create(user=sibling_user, display_name="Astoria", role=Profile.Role.CHILD)
        Wallet.objects.create(child=sibling)
        self.client.force_login(self.child.user)

        response = self.client.post(
            reverse("send_family_transfer"),
            {"recipient_id": sibling.pk, "cash_amount": "1.50"},
            follow=True,
        )

        self.assertRedirects(response, reverse("wallet_page"))
        self.assertContains(response, "payment-success")

    def test_child_can_reserve_spending_for_store_purchase_pending_dad_approval(self):
        self.client.force_login(self.child.user)

        response = self.client.post(
            reverse("request_store_spend"),
            {"cash_amount": "2.25"},
        )

        self.assertRedirects(response, reverse("wallet_page"))
        self.wallet.refresh_from_db()
        entry = LedgerRequest.objects.get(child=self.child, kind=LedgerRequest.Kind.SPEND)
        self.assertEqual(self.wallet.cash_cents, 275)
        self.assertEqual(entry.cash_delta_cents, -225)
        self.assertEqual(entry.status, LedgerRequest.Status.PENDING)

        self.client.force_login(self.guardian.user)
        self.client.post(reverse("review_request", args=[entry.pk, "approve"]))

        self.wallet.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual(self.wallet.cash_cents, 275)
        self.assertEqual(entry.status, LedgerRequest.Status.APPROVED)

    def test_declined_store_spending_refunds_child_balance(self):
        entry = LedgerRequest.objects.create(
            child=self.child,
            requested_by=self.child,
            kind=LedgerRequest.Kind.SPEND,
            description="Store spend pending: $2.25",
            cash_delta_cents=-225,
        )
        self.wallet.cash_cents = 275
        self.wallet.save(update_fields=["cash_cents"])
        self.client.force_login(self.guardian.user)

        self.client.post(reverse("review_request", args=[entry.pk, "decline"]))

        self.wallet.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual(self.wallet.cash_cents, 500)
        self.assertEqual(entry.status, LedgerRequest.Status.DECLINED)

    def test_child_shopping_checkout_reserves_cash_only_and_keeps_tokens(self):
        product = ShoppingProduct.objects.create(
            name="Starter scooter",
            description="Outdoor ride",
            retailer="Google Shopping search",
            retailer_url="https://www.google.com/search?tbm=shop&q=starter+scooter",
            retail_price_cents=225,
            category=ShoppingProduct.Category.OUTDOOR,
        )
        self.client.force_login(self.child.user)

        page = self.client.get(reverse("shopping_page"))
        self.assertContains(page, "Build your cart")
        self.assertContains(page, "Back")
        self.client.post(reverse("shopping_cart_add", args=[product.pk]))
        self.client.post(reverse("shopping_checkout"))

        self.wallet.refresh_from_db()
        order = ShoppingOrder.objects.get(child=self.child)
        ledger = LedgerRequest.objects.get(kind=LedgerRequest.Kind.SHOPPING)
        self.assertEqual(self.wallet.tokens, 20)
        self.assertEqual(self.wallet.cash_cents, 275)
        self.assertEqual(order.quoted_total_cents, 225)
        self.assertEqual(ledger.cash_delta_cents, -225)
        self.assertEqual(ledger.token_delta, 0)
        self.assertEqual(ledger.status, LedgerRequest.Status.PENDING)
        self.assertFalse(ShoppingCartItem.objects.filter(child=self.child).exists())

        self.client.force_login(self.guardian.user)
        self.client.post(reverse("review_request", args=[ledger.pk, "approve"]))
        self.wallet.refresh_from_db()
        ledger.refresh_from_db()
        self.assertEqual(self.wallet.cash_cents, 275)
        self.assertEqual(ledger.status, LedgerRequest.Status.PENDING)

    def test_mom_can_complete_shopping_purchase_but_cannot_edit_catalog(self):
        mom_user = User.objects.create_user(username="mom", password="test")
        mom = Profile.objects.create(user=mom_user, display_name="Mom", role=Profile.Role.VIEWER)
        product = ShoppingProduct.objects.create(
            name="Art kit",
            retailer="Google Shopping search",
            retailer_url="https://www.google.com/search?tbm=shop&q=art+kit",
            retail_price_cents=225,
            category=ShoppingProduct.Category.CREATIVE,
        )
        self.client.force_login(self.child.user)
        self.client.post(reverse("shopping_cart_add", args=[product.pk]))
        self.client.post(reverse("shopping_checkout"))
        order = ShoppingOrder.objects.get(child=self.child)
        self.client.force_login(mom_user)

        dashboard = self.client.get(reverse("dashboard"))
        self.assertContains(dashboard, "Fulfillment")
        self.client.post(reverse("fulfillment_purchase", args=[order.pk]), {"final_amount": "2.00", "parent_note": "Ordered"})
        self.client.post(reverse("dad_shopping_product_stock", args=[product.pk]), {"child_id": self.child.pk})

        self.wallet.refresh_from_db()
        order.refresh_from_db()
        product.refresh_from_db()
        order.reservation_ledger.refresh_from_db()
        self.assertEqual(order.status, ShoppingOrder.Status.PURCHASED)
        self.assertEqual(order.assigned_to, mom)
        self.assertEqual(order.reservation_ledger.status, LedgerRequest.Status.APPROVED)
        self.assertEqual(order.reservation_ledger.cash_delta_cents, -200)
        self.assertEqual(self.wallet.cash_cents, 300)
        self.assertEqual(self.wallet.tokens, 20)
        self.assertTrue(product.in_stock)

    def test_dad_can_mark_shopping_product_out_of_stock_and_delete_it(self):
        product = ShoppingProduct.objects.create(
            name="Temporary listing",
            retailer="Google Shopping search",
            retailer_url="https://www.google.com/search?tbm=shop&q=temporary+listing",
            retail_price_cents=1000,
            category=ShoppingProduct.Category.GAMES,
        )
        self.client.force_login(self.guardian.user)

        self.client.post(reverse("dad_shopping_product_stock", args=[product.pk]), {"child_id": self.child.pk})
        product.refresh_from_db()
        self.assertFalse(product.in_stock)
        self.client.post(reverse("dad_shopping_product_delete", args=[product.pk]), {"child_id": self.child.pk})
        self.assertFalse(ShoppingProduct.objects.filter(pk=product.pk).exists())

    def test_canceling_shopping_order_releases_reserved_cash(self):
        product = ShoppingProduct.objects.create(
            name="Puzzle",
            retailer="Google Shopping search",
            retailer_url="https://www.google.com/search?tbm=shop&q=puzzle",
            retail_price_cents=175,
            category=ShoppingProduct.Category.GAMES,
        )
        self.client.force_login(self.child.user)
        self.client.post(reverse("shopping_cart_add", args=[product.pk]))
        self.client.post(reverse("shopping_checkout"))
        order = ShoppingOrder.objects.get(child=self.child)
        self.client.force_login(self.guardian.user)

        self.client.post(reverse("fulfillment_cancel", args=[order.pk]), {"parent_note": "Unavailable"})

        self.wallet.refresh_from_db()
        order.refresh_from_db()
        order.reservation_ledger.refresh_from_db()
        self.assertEqual(self.wallet.cash_cents, 500)
        self.assertEqual(order.status, ShoppingOrder.Status.CANCELED)
        self.assertEqual(order.reservation_ledger.status, LedgerRequest.Status.DECLINED)

    def test_mixed_price_store_purchase_reduces_inventory_after_parent_approval(self):
        item = StoreItem.objects.create(
            name="Arcade trip",
            token_cost=5,
            cash_cost_cents=100,
            inventory_quantity=1,
            requires_approval=True,
        )
        self.client.force_login(self.child.user)

        self.client.post(reverse("buy_item", args=[item.pk]))

        entry = LedgerRequest.objects.get(store_item=item)
        self.assertTrue(Purchase.objects.filter(ledger=entry, token_cost=5, cash_cost_cents=100).exists())
        item.refresh_from_db()
        self.assertEqual(item.inventory_quantity, 1)

        self.client.force_login(self.guardian.user)
        self.client.post(reverse("review_request", args=[entry.pk, "approve"]))

        self.wallet.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 15)
        self.assertEqual(self.wallet.cash_cents, 400)
        self.assertEqual(item.inventory_quantity, 0)

    def test_child_cannot_send_more_than_available_cash(self):
        sibling_user = User.objects.create_user(username="astoria", password="test")
        sibling = Profile.objects.create(user=sibling_user, display_name="Astoria", role=Profile.Role.CHILD)
        sibling_wallet = Wallet.objects.create(child=sibling)
        self.client.force_login(self.child.user)

        self.client.post(reverse("send_family_transfer"), {"recipient_id": sibling.pk, "cash_amount": "6.00"})

        self.wallet.refresh_from_db()
        sibling_wallet.refresh_from_db()
        self.assertEqual(self.wallet.cash_cents, 500)
        self.assertEqual(self.wallet.spending_cents, 0)
        self.assertEqual(sibling_wallet.cash_cents, 0)
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

    def test_unread_child_notification_appears_on_login_and_recap_dismiss_marks_read(self):
        notice = Notification.objects.create(
            recipient=self.child,
            kind=Notification.Kind.RULE,
            title="House rule updated",
            message="Use kind words.",
        )
        self.client.force_login(self.child.user)

        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "House rule updated")

        self.client.post(reverse("dismiss_recap"))
        notice.refresh_from_db()
        self.assertIsNotNone(notice.read_at)

    def test_child_quest_progress_separates_submitted_from_verified(self):
        Chore.objects.create(child=self.child, title="Submitted", status=Chore.Status.SUBMITTED, due_date=timezone.localdate())
        Chore.objects.create(child=self.child, title="Verified", status=Chore.Status.COMPLETED, due_date=timezone.localdate())
        self.client.force_login(self.child.user)

        response = self.client.get(reverse("child_section", args=["chores"]))

        self.assertEqual(response.context["chore_completed"], 2)
        self.assertEqual(response.context["chore_verified"], 1)
        self.assertContains(response, "guardian verified")
        self.assertContains(response, "data-quest-deadline")

    def test_child_home_keeps_icon_launcher_and_opens_native_app_pages(self):
        self.client.force_login(self.child.user)

        home = self.client.get(reverse("dashboard"))
        quests_url = reverse("child_section", args=["chores"])
        self.assertContains(home, "Home Screen")
        self.assertContains(home, quests_url)
        self.assertNotContains(home, 'data-open-dialog="child-chores"')
        self.assertNotContains(home, 'id="child-chores"')

        quests = self.client.get(quests_url)
        self.assertContains(quests, "Today's Quests")
        self.assertContains(quests, "data-go-back")
        self.assertContains(quests, "Home")
        self.assertNotContains(quests, "<dialog")

    def test_child_chore_action_returns_to_open_native_app(self):
        chore = Chore.objects.create(child=self.child, title="Read a chapter", due_date=timezone.localdate())
        self.client.force_login(self.child.user)

        response = self.client.post(
            reverse("start_chore", args=[chore.pk]),
            {"return_section": "chores"},
        )

        self.assertRedirects(response, reverse("child_section", args=["chores"]))

    def test_messages_icon_shows_unread_and_opening_thread_marks_message_read(self):
        mom_user = User.objects.create_user(username="mom", password="test")
        mom = Profile.objects.create(user=mom_user, display_name="Mom", role=Profile.Role.VIEWER)
        message = FamilyMessage.objects.create(sender=mom, recipient=self.child, body="Dinner is at six.")
        self.client.force_login(self.child.user)

        home = self.client.get(reverse("dashboard"))
        self.assertContains(home, reverse("messages_inbox"))
        self.assertContains(home, "1 new")

        inbox = self.client.get(reverse("messages_inbox"))
        self.assertContains(inbox, "Mom")
        self.assertContains(inbox, "Dinner is at six.")
        self.assertContains(inbox, "Refresh")
        self.assertContains(inbox, "Updated just now")

        thread = self.client.get(reverse("message_thread", args=[mom.pk]))
        self.assertContains(thread, "Dinner is at six.")
        message.refresh_from_db()
        self.assertIsNotNone(message.read_at)

    def test_child_can_message_family_members_and_mom_can_reply(self):
        sibling_user = User.objects.create_user(username="astoria", password="test")
        sibling = Profile.objects.create(user=sibling_user, display_name="Astoria", role=Profile.Role.CHILD)
        Wallet.objects.create(child=sibling)
        mom_user = User.objects.create_user(username="mom", password="test")
        mom = Profile.objects.create(user=mom_user, display_name="Mom", role=Profile.Role.VIEWER)
        self.client.force_login(self.child.user)

        for recipient in (sibling, self.guardian, mom):
            self.client.post(reverse("message_thread", args=[recipient.pk]), {"body": f"Hi {recipient.display_name}"})

        self.assertEqual(FamilyMessage.objects.filter(sender=self.child).count(), 3)
        self.assertTrue(FamilyMessage.objects.filter(sender=self.child, recipient=mom, body="Hi Mom").exists())

        self.client.force_login(mom.user)
        dashboard = self.client.get(reverse("dashboard"))
        self.assertContains(dashboard, reverse("messages_inbox"))
        self.assertContains(dashboard, "Messages")
        self.client.post(reverse("message_thread", args=[self.child.pk]), {"body": "Hi back!"})
        self.assertTrue(FamilyMessage.objects.filter(sender=mom, recipient=self.child, body="Hi back!").exists())

    def test_messages_reject_self_recipient(self):
        with self.assertRaises(ValidationError):
            FamilyMessage.objects.create(sender=self.child, recipient=self.child, body="Note to self")

        self.client.force_login(self.child.user)
        response = self.client.post(reverse("message_thread", args=[self.child.pk]), {"body": "Still no"})
        self.assertRedirects(response, reverse("messages_inbox"))
        self.assertFalse(FamilyMessage.objects.exists())

    def test_guardian_can_create_child_message_and_call_lock_schedule(self):
        self.client.force_login(self.guardian.user)

        response = self.client.post(
            reverse("guardian_communication_schedule"),
            {
                "child_id": self.child.pk,
                "feature": "both",
                "days": ["0", "1", "2", "3", "4"],
                "start_time": "20:00",
                "end_time": "07:00",
                "enabled": "on",
            },
        )

        self.assertRedirects(response, f"/?child={self.child.pk}")
        schedule = CommunicationSchedule.objects.get(child=self.child)
        self.assertEqual(schedule.feature, CommunicationSchedule.Feature.BOTH)
        self.assertEqual(schedule.days_of_week, "0,1,2,3,4")
        self.assertTrue(AuditLog.objects.filter(action="communication_schedule_created", child=self.child).exists())

    @override_settings(LIVEKIT_WS_URL="wss://family.livekit.cloud", LIVEKIT_API_KEY="key", LIVEKIT_API_SECRET="secret")
    def test_active_schedule_blocks_child_messages_and_calls(self):
        mom_user = User.objects.create_user(username="mom", password="test")
        mom = Profile.objects.create(user=mom_user, display_name="Mom", role=Profile.Role.VIEWER)
        CommunicationSchedule.objects.create(
            child=self.child,
            feature=CommunicationSchedule.Feature.BOTH,
            days_of_week="0",
            start_time=time(20, 0),
            end_time=time(22, 0),
            created_by=self.guardian,
        )
        locked_time = timezone.make_aware(datetime(2026, 5, 25, 21, 0))
        self.client.force_login(self.child.user)

        with patch("rewards.models.timezone.now", return_value=locked_time):
            response = self.client.post(reverse("message_thread", args=[mom.pk]), {"body": "Can I call?"}, follow=True)
            call_response = self.client.post(reverse("start_family_call", args=[mom.pk, "video"]), follow=True)

        self.assertContains(response, "Messaging is locked")
        self.assertContains(call_response, "Calling is locked")
        self.assertFalse(FamilyMessage.objects.exists())
        self.assertFalse(FamilyCall.objects.exists())
        active_call = FamilyCall.objects.create(
            caller=self.child,
            recipient=mom,
            call_type=FamilyCall.Type.AUDIO,
            status=FamilyCall.Status.ACTIVE,
        )
        with patch("rewards.models.timezone.now", return_value=locked_time):
            closed_response = self.client.get(reverse("call_status", args=[active_call.pk]))
        active_call.refresh_from_db()
        self.assertEqual(closed_response.json()["reason"], "schedule")
        self.assertEqual(active_call.status, FamilyCall.Status.ENDED)

    @override_settings(LIVEKIT_WS_URL="wss://family.livekit.cloud", LIVEKIT_API_KEY="key", LIVEKIT_API_SECRET="secret")
    @patch("rewards.views._make_livekit_token", return_value="short-lived-token")
    def test_family_video_call_accepts_and_issues_token_only_to_participant(self, token_builder):
        sibling_user = User.objects.create_user(username="astoria", password="test")
        sibling = Profile.objects.create(user=sibling_user, display_name="Astoria", role=Profile.Role.CHILD)
        Wallet.objects.create(child=sibling)
        outsider_user = User.objects.create_user(username="mom", password="test")
        outsider = Profile.objects.create(user=outsider_user, display_name="Mom", role=Profile.Role.VIEWER)
        self.client.force_login(self.child.user)

        self.client.post(reverse("start_family_call", args=[sibling.pk, "video"]))
        call = FamilyCall.objects.get(caller=self.child, recipient=sibling)
        self.assertEqual(call.status, FamilyCall.Status.RINGING)

        self.client.force_login(sibling.user)
        incoming = self.client.get(reverse("call_room", args=[call.pk]))
        self.assertContains(incoming, "Incoming video call")
        self.client.post(reverse("accept_family_call", args=[call.pk]))
        call.refresh_from_db()
        self.assertEqual(call.status, FamilyCall.Status.ACTIVE)
        token_response = self.client.get(reverse("call_token", args=[call.pk]))
        self.assertEqual(token_response.json()["token"], "short-lived-token")
        self.assertEqual(self.client.get(reverse("call_status", args=[call.pk])).json()["status"], FamilyCall.Status.ACTIVE)
        self.client.post(reverse("end_family_call", args=[call.pk]))

        self.client.force_login(self.child.user)
        self.assertEqual(self.client.get(reverse("call_status", args=[call.pk])).json()["status"], FamilyCall.Status.ENDED)
        self.client.force_login(outsider.user)
        forbidden = self.client.get(reverse("call_token", args=[call.pk]))
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(self.client.get(reverse("call_status", args=[call.pk])).status_code, 403)
        token_builder.assert_called_once()

    @override_settings(
        LIVEKIT_WS_URL="wss://family.livekit.cloud",
        LIVEKIT_API_KEY="key",
        LIVEKIT_API_SECRET="secret",
        FREE_CHILD_CALLS_PER_DAY=6,
        CHILD_CALL_TOKEN_COST=1,
    )
    def test_child_gets_six_free_calls_then_new_calls_cost_one_token(self):
        sibling_user = User.objects.create_user(username="call-sibling", password="test")
        sibling = Profile.objects.create(user=sibling_user, display_name="Sibling", role=Profile.Role.CHILD)
        Wallet.objects.create(child=sibling)
        self.client.force_login(self.child.user)

        for _ in range(6):
            self.client.post(reverse("start_family_call", args=[sibling.pk, "audio"]))
            call = FamilyCall.objects.filter(caller=self.child).first()
            self.client.post(reverse("end_family_call", args=[call.pk]))

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 20)
        self.assertFalse(LedgerRequest.objects.filter(child=self.child, kind=LedgerRequest.Kind.CALL).exists())

        self.client.post(reverse("start_family_call", args=[sibling.pk, "video"]))
        self.wallet.refresh_from_db()
        paid_call = FamilyCall.objects.filter(caller=self.child).first()
        self.assertEqual(paid_call.token_cost, 1)
        self.assertEqual(self.wallet.tokens, 19)
        self.assertTrue(LedgerRequest.objects.filter(child=self.child, kind=LedgerRequest.Kind.CALL, token_delta=-1).exists())

    @override_settings(
        LIVEKIT_WS_URL="wss://family.livekit.cloud",
        LIVEKIT_API_KEY="key",
        LIVEKIT_API_SECRET="secret",
        FREE_CHILD_CALLS_PER_DAY=0,
        CHILD_CALL_TOKEN_COST=1,
        CALL_RECONNECT_MINUTES=5,
    )
    @patch("rewards.views._make_livekit_token", return_value="short-lived-token")
    def test_paid_call_reconnects_without_second_charge_until_window_expires(self, token_builder):
        sibling_user = User.objects.create_user(username="reconnect-sibling", password="test")
        sibling = Profile.objects.create(user=sibling_user, display_name="Sibling", role=Profile.Role.CHILD)
        Wallet.objects.create(child=sibling)
        self.client.force_login(self.child.user)

        self.client.post(reverse("start_family_call", args=[sibling.pk, "audio"]))
        call = FamilyCall.objects.get(caller=self.child)
        self.client.get(reverse("call_token", args=[call.pk]))
        self.client.get(reverse("call_token", args=[call.pk]))
        self.wallet.refresh_from_db()
        call.refresh_from_db()
        self.assertIsNotNone(call.access_expires_at)
        self.assertEqual(self.wallet.tokens, 19)
        self.assertEqual(LedgerRequest.objects.filter(kind=LedgerRequest.Kind.CALL).count(), 1)

        call.access_expires_at = timezone.now() - timedelta(seconds=1)
        call.save(update_fields=["access_expires_at"])
        self.assertEqual(self.client.get(reverse("call_token", args=[call.pk])).status_code, 409)
        self.client.post(reverse("start_family_call", args=[sibling.pk, "audio"]))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 18)
        self.assertEqual(LedgerRequest.objects.filter(kind=LedgerRequest.Kind.CALL).count(), 2)

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
        self.client.post(reverse("dad_approve_schedule"), {"child_id": self.child.pk, "day": today})

        self.client.force_login(self.child.user)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Today's Plan")
        self.assertContains(response, "Library visit")
        self.assertContains(response, "Pack homework")
        self.assertContains(response, "Kind voices")

    def test_draft_schedule_is_hidden_from_child_until_dad_publishes_current_day(self):
        event = DailyScheduleEvent.objects.create(
            child=self.child,
            day=timezone.localdate(),
            title="Dance practice",
            details="Bring shoes.",
            created_by=self.guardian,
        )
        self.client.force_login(self.child.user)

        response = self.client.get(reverse("dashboard"))
        self.assertNotContains(response, "Dance practice")

        self.client.force_login(self.guardian.user)
        self.client.post(reverse("dad_approve_schedule"), {"child_id": self.child.pk, "day": event.day.isoformat()})
        self.client.force_login(self.child.user)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Dance practice")

    def test_guardian_can_delete_a_personal_rule(self):
        rule = ChildRule.objects.create(child=self.child, title="Temporary reminder")
        self.client.force_login(self.guardian.user)

        self.client.post(reverse("guardian_remove", args=["child_rule", rule.pk]))

        self.assertFalse(ChildRule.objects.filter(pk=rule.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action="child_rule_deleted", child=self.child).exists())

    def test_child_acknowledges_rules_and_parent_edit_requires_fresh_acknowledgement(self):
        rule = HouseRule.objects.create(title="Use kind words", created_by=self.guardian)
        self.client.force_login(self.child.user)

        self.client.post(reverse("acknowledge_rule", args=["house_rule", rule.pk]))

        self.assertTrue(RuleAcknowledgement.objects.filter(child=self.child, house_rule=rule).exists())
        self.client.force_login(self.guardian.user)
        self.client.post(
            reverse("guardian_edit", args=["house_rule", rule.pk]),
            {"child_id": self.child.pk, "title": "Use kind words", "details": "At home and outside.", "consequence": "Pause game time."},
        )
        self.assertFalse(RuleAcknowledgement.objects.filter(child=self.child, house_rule=rule).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.child, kind=Notification.Kind.RULE).exists())

    def test_expired_individual_rule_is_hidden_from_child(self):
        ChildRule.objects.create(
            child=self.child,
            title="Temporary bedtime",
            expires_on=timezone.localdate() - timedelta(days=1),
            created_by=self.guardian,
        )
        self.client.force_login(self.child.user)

        response = self.client.get(reverse("dashboard"))

        self.assertNotContains(response, "Temporary bedtime")

    def test_grounded_mode_hides_child_wallet_and_verifies_chores_without_rewards(self):
        chore = Chore.objects.create(child=self.child, title="Put away backpack", token_reward=4)
        self.client.force_login(self.guardian.user)
        self.client.post(
            reverse("guardian_lockdown"),
            {"child_id": self.child.pk, "action": "lock", "reason": "Focus on chores today."},
        )
        self.child.refresh_from_db()
        self.assertTrue(self.child.grounded)
        self.assertEqual(BehaviorNote.objects.get(child=self.child).title, "Grounded Mode issued")

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

    def test_guardian_can_remove_active_grounding_punishment_record(self):
        self.client.force_login(self.guardian.user)
        self.client.post(
            reverse("guardian_lockdown"),
            {"child_id": self.child.pk, "action": "lock", "reason": "Incorrect test consequence."},
        )
        note = BehaviorNote.objects.get(child=self.child)

        self.client.post(reverse("guardian_remove_behavior_note", args=[note.pk]))

        self.child.refresh_from_db()
        self.assertFalse(self.child.grounded)
        self.assertFalse(BehaviorNote.objects.filter(pk=note.pk).exists())
        self.assertTrue(AuditLog.objects.filter(child=self.child, action="behavior_note_removed").exists())

    def test_guardian_can_reverse_token_punishment_once_without_deleting_history(self):
        self.client.force_login(self.guardian.user)
        self.client.post(
            reverse("guardian_behavior_deduction"),
            {"child_id": self.child.pk, "reason": "Test deduction", "tokens": "4"},
        )
        punishment = LedgerRequest.objects.get(kind=LedgerRequest.Kind.BEHAVIOR)
        self.child.last_recap_at = timezone.now() - timedelta(days=1)
        self.child.last_recap_day = timezone.localdate() - timedelta(days=1)
        self.child.save(update_fields=["last_recap_at", "last_recap_day"])

        self.client.post(reverse("guardian_reverse_punishment", args=[punishment.pk]))
        self.client.post(reverse("guardian_reverse_punishment", args=[punishment.pk]))

        self.wallet.refresh_from_db()
        punishment.refresh_from_db()
        self.assertEqual(self.wallet.tokens, 20)
        self.assertTrue(LedgerRequest.objects.filter(reversal_of=punishment, kind=LedgerRequest.Kind.REVERSAL).exists())
        self.assertEqual(LedgerRequest.objects.filter(reversal_of=punishment).count(), 1)
        self.assertTrue(AuditLog.objects.filter(child=self.child, action="punishment_reversed").exists())
        self.client.force_login(self.child.user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["recap_token_loss"], 0)
        self.assertEqual(response.context["recap_token_total"], 0)

    def test_gg_sees_calendar_but_only_dad_can_create_or_publish_schedule(self):
        gg_user = User.objects.create_user(username="gg", password="test")
        gg = Profile.objects.create(user=gg_user, display_name="GG", role=Profile.Role.GUARDIAN)
        day = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.client.force_login(gg.user)
        self.client.post(
            reverse("guardian_create", args=["schedule"]),
            {"child_id": self.child.pk, "day": day, "title": "Future plan", "details": ""},
        )
        self.assertFalse(DailyScheduleEvent.objects.filter(title="Future plan").exists())
        self.assertContains(self.client.get(reverse("dashboard")), "Family Calendar")

        self.client.force_login(self.guardian.user)
        self.client.post(
            reverse("guardian_create", args=["schedule"]),
            {"child_id": self.child.pk, "day": day, "title": "Future plan", "details": ""},
        )
        event = DailyScheduleEvent.objects.get(title="Future plan")
        self.client.force_login(gg.user)
        gg_dashboard = self.client.get(reverse("dashboard"))
        self.assertContains(gg_dashboard, "Upcoming event queue")
        self.assertContains(gg_dashboard, "Future plan")
        self.client.post(reverse("dad_approve_schedule"), {"child_id": self.child.pk, "day": day})
        event.refresh_from_db()
        self.assertIsNone(event.approved_at)

        self.client.force_login(self.guardian.user)
        self.client.post(reverse("dad_approve_schedule"), {"child_id": self.child.pk, "day": day})
        event.refresh_from_db()
        self.assertIsNotNone(event.approved_at)

        self.client.force_login(self.child.user)
        self.assertNotContains(self.client.get(reverse("dashboard")), "Future plan")

    def test_scheduled_grounding_auto_lifts_and_note_is_visible_to_mom(self):
        lift_at = timezone.now() + timedelta(hours=2)
        self.client.force_login(self.guardian.user)
        self.client.post(
            reverse("guardian_lockdown"),
            {"child_id": self.child.pk, "action": "lock", "reason": "Directions were not followed.", "lift_at": lift_at.strftime("%Y-%m-%dT%H:%M")},
        )
        note = BehaviorNote.objects.get(child=self.child)
        self.assertEqual(note.issued_by, self.guardian)
        self.assertIn("Directions", note.note)

        mom_user = User.objects.create_user(username="mom", password="test")
        mom = Profile.objects.create(user=mom_user, display_name="Mom", role=Profile.Role.VIEWER)
        self.client.force_login(mom.user)
        self.assertContains(self.client.get(reverse("dashboard")), "Grounded Mode issued")

        self.child.grounded_until = timezone.now() - timedelta(minutes=1)
        self.child.save(update_fields=["grounded_until"])
        self.client.force_login(self.child.user)
        self.client.get(reverse("dashboard"))
        self.child.refresh_from_db()
        self.assertFalse(self.child.grounded)

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
        self.assertNotContains(response, "Open Family Calendar")

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

        self.assertEqual(Chore.objects.filter(due_date=date(2026, 5, 24)).count(), 18)
        for child in Profile.objects.filter(role=Profile.Role.CHILD):
            self.assertEqual(child.chores.filter(due_date=date(2026, 5, 24), optional=False).count(), 4)
            bonuses = child.chores.filter(due_date=date(2026, 5, 24), optional=True)
            self.assertEqual(bonuses.count(), 2)
            self.assertSetEqual(set(bonuses.values_list("title", flat=True)), {"Make your bed", "Dress yourself"})
            self.assertTrue(all(bonus.credit_deadline == time(10, 0) for bonus in bonuses))

    @patch("rewards.services.timezone.localdate", return_value=date(2026, 5, 24))
    def test_daily_chores_create_one_login_notification_per_child(self, mocked_date):
        ensure_today_chores()
        ensure_today_chores()

        for child in Profile.objects.filter(role=Profile.Role.CHILD):
            self.assertEqual(child.notifications.filter(kind=Notification.Kind.CHORE).count(), 1)
