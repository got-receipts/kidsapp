from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Chore, LedgerRequest, Profile, Wallet


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
