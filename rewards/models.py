from datetime import time
import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone


class Profile(models.Model):
    class Role(models.TextChoices):
        CHILD = "child", "Child"
        GUARDIAN = "guardian", "Guardian"
        VIEWER = "viewer", "Family viewer"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=40)
    role = models.CharField(max_length=10, choices=Role.choices)
    birth_date = models.DateField(null=True, blank=True)
    last_recap_at = models.DateTimeField(null=True, blank=True)
    last_recap_day = models.DateField(null=True, blank=True)
    grounded = models.BooleanField(default=False)
    grounded_reason = models.CharField(max_length=180, blank=True)
    grounded_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="grounded_children")
    grounded_at = models.DateTimeField(null=True, blank=True)
    grounded_until = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.display_name

    @property
    def is_guardian(self):
        return self.role == self.Role.GUARDIAN

    @property
    def can_view_family(self):
        return self.role in [self.Role.GUARDIAN, self.Role.VIEWER]

    def refresh_grounding(self):
        if self.grounded and self.grounded_until and self.grounded_until <= timezone.now():
            self.grounded = False
            self.grounded_reason = ""
            self.grounded_by = None
            self.grounded_at = None
            self.grounded_until = None
            self.save(update_fields=["grounded", "grounded_reason", "grounded_by", "grounded_at", "grounded_until"])
        return self.grounded


class Wallet(models.Model):
    child = models.OneToOneField(Profile, on_delete=models.CASCADE, related_name="wallet")
    tokens = models.IntegerField(default=0)
    cash_cents = models.PositiveIntegerField(default=0)
    spending_cents = models.PositiveIntegerField(default=0)

    @property
    def available_cash_cents(self):
        return self.cash_cents + self.spending_cents

    def __str__(self):
        return f"{self.child.display_name}'s wallet"


class FamilySettings(models.Model):
    tokens_per_dollar = models.PositiveIntegerField(default=10)
    updated_by = models.ForeignKey(
        Profile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="family_settings_updates",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.tokens_per_dollar < 1:
            raise ValidationError("Token exchange rate must be at least 1 token per dollar.")

    @classmethod
    def load(cls):
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings

    def __str__(self):
        return f"{self.tokens_per_dollar} tokens = $1.00"


class SavingsGoal(models.Model):
    child = models.OneToOneField(Profile, on_delete=models.CASCADE, related_name="savings_goal")
    name = models.CharField(max_length=80)
    target_cents = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def saved_cents(self):
        return self.child.wallet.cash_cents

    @property
    def remaining_cents(self):
        return max(self.target_cents - self.saved_cents, 0)

    @property
    def percent(self):
        if not self.target_cents:
            return 0
        return min(round(self.saved_cents / self.target_cents * 100), 100)

    @property
    def reached(self):
        return self.saved_cents >= self.target_cents

    def __str__(self):
        return f"{self.child.display_name}: {self.name}"


class DailyScheduleEvent(models.Model):
    child = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="schedule_events")
    day = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    title = models.CharField(max_length=100)
    details = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="events_created")
    approved_by = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="schedules_approved")
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["day", "start_time", "created_at"]

    def __str__(self):
        return f"{self.child.display_name}: {self.title}"


class ChildRule(models.Model):
    child = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="specific_rules")
    title = models.CharField(max_length=100)
    details = models.CharField(max_length=240, blank=True)
    consequence = models.CharField(max_length=240, blank=True)
    active = models.BooleanField(default=True)
    expires_on = models.DateField(null=True, blank=True)
    scheduled_remove_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="child_rules_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.child.display_name}: {self.title}"

    @property
    def is_current(self):
        if not self.active:
            return False
        if self.expires_on and self.expires_on < timezone.localdate():
            return False
        return not self.scheduled_remove_at or self.scheduled_remove_at > timezone.now()


class HouseRule(models.Model):
    title = models.CharField(max_length=100)
    details = models.CharField(max_length=240, blank=True)
    consequence = models.CharField(max_length=240, blank=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="house_rules_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.title


class RuleAcknowledgement(models.Model):
    child = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="rule_acknowledgements")
    house_rule = models.ForeignKey(
        HouseRule,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="acknowledgements",
    )
    child_rule = models.ForeignKey(
        ChildRule,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="acknowledgements",
    )
    acknowledged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(house_rule__isnull=False, child_rule__isnull=True) | Q(house_rule__isnull=True, child_rule__isnull=False)),
                name="acknowledges_one_rule_type",
            ),
            models.UniqueConstraint(
                fields=["child", "house_rule"],
                condition=Q(house_rule__isnull=False),
                name="one_house_rule_ack_per_child",
            ),
            models.UniqueConstraint(
                fields=["child", "child_rule"],
                condition=Q(child_rule__isnull=False),
                name="one_child_rule_ack_per_child",
            ),
        ]

    def clean(self):
        if self.child.role != Profile.Role.CHILD:
            raise ValidationError("Only child profiles acknowledge rules.")
        if self.child_rule and self.child_rule.child_id != self.child_id:
            raise ValidationError("A child may only acknowledge their own individual rule.")


class BehaviorNote(models.Model):
    child = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="behavior_notes")
    issued_by = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="behavior_notes_issued")
    title = models.CharField(max_length=80)
    note = models.CharField(max_length=240, blank=True)
    negative = models.BooleanField(default=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    scheduled_lift_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return f"{self.child.display_name}: {self.title}"


class Grade(models.Model):
    child = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="grades")
    subject = models.CharField(max_length=60)
    assignment = models.CharField(max_length=100)
    score = models.DecimalField(max_digits=5, decimal_places=2)
    maximum_score = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    recorded_by = models.ForeignKey(Profile, null=True, on_delete=models.SET_NULL, related_name="grades_recorded")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def percent(self):
        return round((self.score / self.maximum_score) * 100) if self.maximum_score else 0


class Chore(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "To do"
        IN_PROGRESS = "in_progress", "Working on it"
        SUBMITTED = "submitted", "Waiting approval"
        COMPLETED = "completed", "Completed"
        LATE = "late", "Completed after deadline"
        NOT_VERIFIED = "not_verified", "Not verified - points lost"

    child = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="chores")
    title = models.CharField(max_length=100)
    instructions = models.CharField(max_length=240, blank=True)
    token_reward = models.PositiveIntegerField(default=0)
    cash_reward_cents = models.PositiveIntegerField(default=0)
    optional = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    due_date = models.DateField(null=True, blank=True)
    credit_deadline = models.TimeField(default=time(19, 0))
    assigned_by = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="chores_assigned")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["child", "title", "due_date"], name="one_daily_chore_assignment"),
            models.CheckConstraint(condition=Q(cash_reward_cents=0), name="chore_rewards_tokens_only"),
        ]


class GrowthGoal(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Working on it"
        SUBMITTED = "submitted", "Waiting approval"
        COMPLETED = "completed", "Completed"

    child = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="goals")
    title = models.CharField(max_length=100)
    encouragement = models.CharField(max_length=240, blank=True)
    token_reward = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)


class StoreItem(models.Model):
    class Category(models.TextChoices):
        TREAT = "treat", "Treat"
        EXPERIENCE = "experience", "Adventure"
        GRAND = "grand", "Grand prize"

    name = models.CharField(max_length=100)
    description = models.CharField(max_length=180, blank=True)
    token_cost = models.PositiveIntegerField(default=0)
    cash_cost_cents = models.PositiveIntegerField(default=0)
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.TREAT)
    active = models.BooleanField(default=True)
    hidden = models.BooleanField(default=False)
    token_unlock_threshold = models.PositiveIntegerField(default=0)
    inventory_quantity = models.PositiveIntegerField(null=True, blank=True)
    minimum_age = models.PositiveSmallIntegerField(null=True, blank=True)
    requires_approval = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def clean(self):
        if not self.token_cost and not self.cash_cost_cents:
            raise ValidationError("Store items must cost tokens, cash, or both.")

    def available_to(self, child):
        if not self.active or self.hidden:
            return False
        if self.inventory_quantity is not None and self.inventory_quantity < 1:
            return False
        if child.wallet.tokens < self.token_unlock_threshold:
            return False
        if self.minimum_age and child.birth_date:
            today = timezone.localdate()
            age = today.year - child.birth_date.year - ((today.month, today.day) < (child.birth_date.month, child.birth_date.day))
            return age >= self.minimum_age
        return not self.minimum_age


class ShoppingProduct(models.Model):
    class Category(models.TextChoices):
        BUILDING = "building", "Building sets"
        STEM = "stem", "STEM & learning"
        CREATIVE = "creative", "Arts & crafts"
        GAMES = "games", "Games & puzzles"
        OUTDOOR = "outdoor", "Outdoor play"
        ELECTRONICS = "electronics", "Kids electronics"
        PRETEND = "pretend", "Pretend play"

    name = models.CharField(max_length=120)
    description = models.CharField(max_length=220, blank=True)
    retailer = models.CharField(max_length=60, default="Google Shopping")
    retailer_url = models.URLField(max_length=500)
    image_url = models.URLField(max_length=500, blank=True)
    retail_price_cents = models.PositiveIntegerField()
    category = models.CharField(max_length=14, choices=Category.choices)
    active = models.BooleanField(default=True)
    in_stock = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    minimum_age = models.PositiveSmallIntegerField(null=True, blank=True)
    added_by = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="shopping_products_added")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return self.name

    def available_to(self, child):
        if not self.active or not self.in_stock:
            return False
        if self.minimum_age and child.birth_date:
            today = timezone.localdate()
            age = today.year - child.birth_date.year - ((today.month, today.day) < (child.birth_date.month, child.birth_date.day))
            return age >= self.minimum_age
        return not self.minimum_age


class ShoppingCartItem(models.Model):
    child = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="shopping_cart_items")
    product = models.ForeignKey(ShoppingProduct, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveSmallIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    @property
    def subtotal_cents(self):
        return self.product.retail_price_cents * self.quantity

    class Meta:
        ordering = ["added_at"]
        constraints = [
            models.UniqueConstraint(fields=["child", "product"], name="one_product_per_child_shopping_cart"),
            models.CheckConstraint(condition=Q(quantity__gte=1), name="shopping_cart_quantity_at_least_one"),
        ]


class ShoppingOrder(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Sent to parent"
        CLAIMED = "claimed", "Being purchased"
        PURCHASED = "purchased", "Purchased"
        CANCELED = "canceled", "Canceled"
        DELIVERED = "delivered", "Delivered"

    child = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="shopping_orders")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SUBMITTED)
    assigned_to = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="shopping_orders_assigned")
    reservation_ledger = models.OneToOneField(
        "LedgerRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="shopping_order",
    )
    quoted_total_cents = models.PositiveIntegerField()
    held_cash_cents = models.PositiveIntegerField(default=0)
    held_spending_cents = models.PositiveIntegerField(default=0)
    final_total_cents = models.PositiveIntegerField(null=True, blank=True)
    parent_note = models.CharField(max_length=240, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    purchased_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    @property
    def reserved_total_cents(self):
        return self.held_cash_cents + self.held_spending_cents

    class Meta:
        ordering = ["-submitted_at"]


class ShoppingOrderItem(models.Model):
    order = models.ForeignKey(ShoppingOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(ShoppingProduct, null=True, blank=True, on_delete=models.SET_NULL, related_name="order_items")
    product_name = models.CharField(max_length=120)
    retailer = models.CharField(max_length=60)
    retailer_url = models.URLField(max_length=500)
    image_url = models.URLField(max_length=500, blank=True)
    unit_price_cents = models.PositiveIntegerField()
    quantity = models.PositiveSmallIntegerField(default=1)

    @property
    def subtotal_cents(self):
        return self.unit_price_cents * self.quantity

    class Meta:
        ordering = ["pk"]


class BehaviorStar(models.Model):
    child = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="behavior_stars")
    awarded_by = models.ForeignKey(Profile, null=True, on_delete=models.SET_NULL, related_name="stars_awarded")
    day = models.DateField()
    note = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["child", "day"], name="one_behavior_star_per_child_day")
        ]
        ordering = ["-day"]


class LedgerRequest(models.Model):
    class Kind(models.TextChoices):
        CHORE = "chore", "Chore reward"
        GOAL = "goal", "Growth goal reward"
        STORE = "store", "Store purchase"
        SPEND = "spend", "Spend money"
        CONVERT = "convert", "Legacy conversion (disabled)"
        CASH_OUT = "cash_out", "Cash out"
        AWARD = "award", "Guardian award"
        STAR = "star", "Good behavior star"
        TRANSFER = "transfer", "Move to spending"
        BALANCE = "balance", "Balance correction"
        PENALTY = "penalty", "Quest not verified"
        BEHAVIOR = "behavior", "Behavior deduction"
        GIFT = "gift", "Family transfer"
        CALL = "call", "Family call"
        REVERSAL = "reversal", "Punishment removed"
        SHOPPING = "shopping", "Shopping order"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting"
        APPROVED = "approved", "Approved"
        DECLINED = "declined", "Declined"

    child = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="ledger_requests")
    requested_by = models.ForeignKey(Profile, null=True, on_delete=models.SET_NULL, related_name="requests_made")
    reviewed_by = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="requests_reviewed")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    description = models.CharField(max_length=160)
    token_delta = models.IntegerField(default=0)
    cash_delta_cents = models.IntegerField(default=0)
    spending_delta_cents = models.IntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    chore = models.OneToOneField(Chore, null=True, blank=True, on_delete=models.SET_NULL)
    goal = models.OneToOneField(GrowthGoal, null=True, blank=True, on_delete=models.SET_NULL)
    behavior_star = models.OneToOneField(BehaviorStar, null=True, blank=True, on_delete=models.SET_NULL)
    store_item = models.ForeignKey(StoreItem, null=True, blank=True, on_delete=models.SET_NULL)
    counterparty = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="transfers_with")
    reversal_of = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reversal",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def requires_dad_approval(self):
        # These are retained for the spendable-cash flow. New token cash-outs
        # post immediately and never enter the approval queue.
        return self.kind in [self.Kind.TRANSFER, self.Kind.CONVERT, self.Kind.SPEND]

    @property
    def reserves_spending_immediately(self):
        return self.kind in [self.Kind.SPEND, self.Kind.SHOPPING] and (
            self.cash_delta_cents < 0 or self.spending_delta_cents < 0
        )

    @property
    def money_delta_cents(self):
        return self.cash_delta_cents + self.spending_delta_cents

    @property
    def can_reverse_punishment(self):
        if self.kind not in [self.Kind.PENALTY, self.Kind.BEHAVIOR] or self.status != self.Status.APPROVED or self.token_delta >= 0:
            return False
        try:
            self.reversal
        except LedgerRequest.DoesNotExist:
            return True
        return False

    def approve(self, guardian=None):
        from django.utils import timezone

        instant_store_purchase = self.kind == self.Kind.STORE and self.store_item and not self.store_item.requires_approval
        if guardian is None and not instant_store_purchase:
            raise ValidationError("Only guardians can approve requests.")
        if guardian is not None and not guardian.is_guardian:
            raise ValidationError("Only guardians can approve requests.")
        if guardian is not None and self.requires_dad_approval and guardian.user.username.lower() != "dad":
            raise ValidationError("Only Dad can approve wallet-to-spending and spending requests.")
        with transaction.atomic():
            request = LedgerRequest.objects.select_for_update().get(pk=self.pk)
            if request.status != self.Status.PENDING:
                return
            if request.kind == self.Kind.CHORE and request.cash_delta_cents:
                raise ValidationError("Chores award tokens only; they cannot create cash.")
            if request.kind == self.Kind.CONVERT and (request.token_delta > 0 or request.cash_delta_cents < 0):
                raise ValidationError("Wallet cash cannot be converted back into tokens.")
            request.child.refresh_grounding()
            changes_balance = bool(request.token_delta or request.cash_delta_cents or request.spending_delta_cents)
            if request.child.grounded and changes_balance and request.kind not in [self.Kind.BALANCE, self.Kind.REVERSAL]:
                raise ValidationError("This account is in Grounded Mode. Unlock it before posting rewards or spending.")
            if request.reserves_spending_immediately:
                Wallet.objects.select_for_update().get(child=request.child)
            else:
                wallet = Wallet.objects.select_for_update().get(child=request.child)
                if request.kind not in [self.Kind.PENALTY, self.Kind.BEHAVIOR] and wallet.tokens + request.token_delta < 0:
                    raise ValidationError("Not enough tokens for this request.")
                if wallet.cash_cents + request.cash_delta_cents < 0:
                    raise ValidationError("Not enough cash balance for this request.")
                if wallet.spending_cents + request.spending_delta_cents < 0:
                    raise ValidationError("Not enough spending balance for this request.")
                Wallet.objects.filter(pk=wallet.pk).update(
                    tokens=F("tokens") + request.token_delta,
                    cash_cents=F("cash_cents") + request.cash_delta_cents,
                    spending_cents=F("spending_cents") + request.spending_delta_cents,
                )
            if request.kind == self.Kind.STORE and request.store_item_id:
                item = StoreItem.objects.select_for_update().get(pk=request.store_item_id)
                if item.inventory_quantity is not None:
                    if item.inventory_quantity < 1:
                        raise ValidationError("This item is out of stock.")
                    StoreItem.objects.filter(pk=item.pk).update(inventory_quantity=F("inventory_quantity") - 1)
            request.status = self.Status.APPROVED
            request.reviewed_by = guardian
            request.reviewed_at = timezone.now()
            request.save(update_fields=["status", "reviewed_by", "reviewed_at"])
            if request.chore:
                request.chore.status = Chore.Status.COMPLETED
                request.chore.save(update_fields=["status"])
            if request.goal:
                request.goal.status = GrowthGoal.Status.COMPLETED
                request.goal.save(update_fields=["status"])
            Purchase.objects.filter(ledger=request).update(fulfilled_at=request.reviewed_at)
            notification_kind = {
                self.Kind.STORE: Notification.Kind.STORE,
                self.Kind.CASH_OUT: Notification.Kind.WALLET,
                self.Kind.TRANSFER: Notification.Kind.WALLET,
                self.Kind.SPEND: Notification.Kind.WALLET,
                self.Kind.BALANCE: Notification.Kind.WALLET,
                self.Kind.CHORE: Notification.Kind.REWARD,
                self.Kind.CALL: Notification.Kind.CALL,
            }.get(request.kind, Notification.Kind.REWARD)
            notification_title = {
                self.Kind.CHORE: "Chore approved - tokens earned",
                self.Kind.CASH_OUT: "Wallet cash-out approved",
                self.Kind.STORE: "Store purchase approved",
                self.Kind.AWARD: "New parent reward",
                self.Kind.BEHAVIOR: "Token balance updated",
                self.Kind.BALANCE: "Wallet balance updated",
                self.Kind.REVERSAL: "Punishment removed",
            }.get(request.kind, "Reward approved")
            Notification.objects.create(
                recipient=request.child,
                kind=notification_kind,
                title=notification_title,
                message=request.description,
            )
            AuditLog.objects.create(
                actor=guardian,
                child=request.child,
                ledger=request,
                action="request_approved",
                description=request.description,
            )

    def decline(self, guardian):
        from django.utils import timezone

        if not guardian.is_guardian:
            raise ValidationError("Only guardians can decline requests.")
        with transaction.atomic():
            request = LedgerRequest.objects.select_for_update().get(pk=self.pk)
            if request.status != self.Status.PENDING:
                return
            if request.reserves_spending_immediately:
                wallet = Wallet.objects.select_for_update().get(child=request.child)
                Wallet.objects.filter(pk=wallet.pk).update(
                    cash_cents=F("cash_cents") - request.cash_delta_cents,
                    spending_cents=F("spending_cents") - request.spending_delta_cents,
                )
            request.status = self.Status.DECLINED
            request.reviewed_by = guardian
            request.reviewed_at = timezone.now()
            request.save(update_fields=["status", "reviewed_by", "reviewed_at"])
            if request.chore:
                request.chore.status = Chore.Status.NOT_VERIFIED
                request.chore.save(update_fields=["status"])
                if request.chore.token_reward and request.token_delta > 0 and not request.child.grounded:
                    Wallet.objects.filter(child=request.child).update(tokens=F("tokens") - request.chore.token_reward)
                    LedgerRequest.objects.create(
                        child=request.child,
                        requested_by=guardian,
                        reviewed_by=guardian,
                        reviewed_at=timezone.now(),
                        kind=self.Kind.PENALTY,
                        description=f"Not verified: {request.chore.title}",
                        token_delta=-request.chore.token_reward,
                        status=self.Status.APPROVED,
                    )
            if request.goal:
                request.goal.status = GrowthGoal.Status.ACTIVE
                request.goal.save(update_fields=["status"])
            declined_kind = {
                self.Kind.CASH_OUT: Notification.Kind.WALLET,
                self.Kind.STORE: Notification.Kind.STORE,
                self.Kind.TRANSFER: Notification.Kind.WALLET,
                self.Kind.SPEND: Notification.Kind.WALLET,
            }.get(request.kind, Notification.Kind.REWARD)
            Notification.objects.create(
                recipient=request.child,
                kind=declined_kind,
                title="Request not approved",
                message=request.description,
            )
            AuditLog.objects.create(
                actor=guardian,
                child=request.child,
                ledger=request,
                action="request_declined",
                description=request.description,
            )


class Purchase(models.Model):
    child = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="purchases")
    item = models.ForeignKey(StoreItem, null=True, on_delete=models.SET_NULL, related_name="purchases")
    ledger = models.OneToOneField(LedgerRequest, on_delete=models.CASCADE, related_name="purchase")
    token_cost = models.PositiveIntegerField(default=0)
    cash_cost_cents = models.PositiveIntegerField(default=0)
    requested_at = models.DateTimeField(auto_now_add=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]


class Notification(models.Model):
    class Kind(models.TextChoices):
        CHORE = "chore", "New chore"
        REWARD = "reward", "Token reward"
        RULE = "rule", "Rule update"
        GROUNDED = "grounded", "Grounded mode"
        WALLET = "wallet", "Wallet update"
        STORE = "store", "Store purchase"
        MESSAGE = "message", "Message"
        CALL = "call", "Call"
        SHOPPING = "shopping", "Shopping order"

    recipient = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    title = models.CharField(max_length=80)
    message = models.CharField(max_length=240)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class FamilyMessage(models.Model):
    sender = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="sent_family_messages")
    recipient = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="received_family_messages")
    body = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        if self.sender_id and self.sender_id == self.recipient_id:
            raise ValidationError("You cannot send a message to yourself.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(sender=F("recipient")),
                name="family_message_recipient_differs_from_sender",
            )
        ]
        indexes = [
            models.Index(fields=["recipient", "read_at"], name="message_unread_idx"),
            models.Index(fields=["sender", "recipient", "created_at"], name="message_thread_idx"),
        ]


class CommunicationSchedule(models.Model):
    class Feature(models.TextChoices):
        MESSAGING = "messaging", "Messages only"
        CALLING = "calling", "Calls only"
        BOTH = "both", "Messages and calls"

    WEEKDAYS = [
        ("0", "Monday"),
        ("1", "Tuesday"),
        ("2", "Wednesday"),
        ("3", "Thursday"),
        ("4", "Friday"),
        ("5", "Saturday"),
        ("6", "Sunday"),
    ]

    child = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="communication_schedules")
    feature = models.CharField(max_length=12, choices=Feature.choices, default=Feature.BOTH)
    days_of_week = models.CharField(max_length=20, default="0,1,2,3,4,5,6")
    start_time = models.TimeField()
    end_time = models.TimeField()
    enabled = models.BooleanField(default=True)
    created_by = models.ForeignKey(Profile, null=True, on_delete=models.SET_NULL, related_name="communication_schedules_created")
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.child_id and self.child.role != Profile.Role.CHILD:
            raise ValidationError("Communication schedules apply only to child accounts.")
        valid_days = {day for day, _ in self.WEEKDAYS}
        if not set(filter(None, self.days_of_week.split(","))).issubset(valid_days):
            raise ValidationError("Select valid schedule days.")

    def applies_at(self, moment=None):
        if not self.enabled:
            return False
        moment = timezone.localtime(moment or timezone.now())
        selected_days = set(filter(None, self.days_of_week.split(",")))
        current_day = str(moment.weekday())
        current_time = moment.time().replace(tzinfo=None)
        if self.start_time <= self.end_time:
            return current_day in selected_days and self.start_time <= current_time < self.end_time
        if current_time >= self.start_time:
            return current_day in selected_days
        previous_day = str((moment.weekday() - 1) % 7)
        return current_time < self.end_time and previous_day in selected_days

    @property
    def days_display(self):
        selected_days = set(filter(None, self.days_of_week.split(",")))
        return ", ".join(label[:3] for value, label in self.WEEKDAYS if value in selected_days)

    class Meta:
        ordering = ["child__display_name", "start_time"]


def new_call_room_name():
    return f"family-call-{uuid.uuid4().hex}"


class FamilyCall(models.Model):
    class Type(models.TextChoices):
        AUDIO = "audio", "Audio"
        VIDEO = "video", "Video"

    class Status(models.TextChoices):
        RINGING = "ringing", "Ringing"
        ACTIVE = "active", "Active"
        DECLINED = "declined", "Declined"
        ENDED = "ended", "Ended"

    caller = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="calls_started")
    recipient = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="calls_received")
    call_type = models.CharField(max_length=8, choices=Type.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RINGING)
    room_name = models.CharField(max_length=80, unique=True, default=new_call_room_name, editable=False)
    allowance_day = models.DateField(null=True, blank=True)
    token_cost = models.PositiveSmallIntegerField(default=0)
    access_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        if self.caller_id and self.caller_id == self.recipient_id:
            raise ValidationError("You cannot call yourself.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def includes(self, profile):
        return profile.pk in {self.caller_id, self.recipient_id}

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(caller=F("recipient")),
                name="family_call_recipient_differs_from_caller",
            )
        ]


class AuditLog(models.Model):
    actor = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_actions")
    child = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_entries")
    ledger = models.ForeignKey(LedgerRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_entries")
    house_rule = models.ForeignKey(HouseRule, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_entries")
    child_rule = models.ForeignKey(ChildRule, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_entries")
    action = models.CharField(max_length=40)
    description = models.CharField(max_length=240)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PushSubscription(models.Model):
    guardian = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.TextField(unique=True)
    p256dh = models.TextField()
    auth = models.TextField()
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ReminderDispatch(models.Model):
    day = models.DateField(unique=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    recipient_count = models.PositiveIntegerField(default=0)


class ScheduleReminderDispatch(models.Model):
    day = models.DateField(unique=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    recipient_count = models.PositiveIntegerField(default=0)
