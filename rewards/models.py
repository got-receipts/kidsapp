from datetime import time

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
        return self.kind == self.Kind.SPEND and self.spending_delta_cents < 0

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
            if request.child.grounded and changes_balance and request.kind != self.Kind.BALANCE:
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
            }.get(request.kind, Notification.Kind.REWARD)
            notification_title = {
                self.Kind.CHORE: "Chore approved - tokens earned",
                self.Kind.CASH_OUT: "Wallet cash-out approved",
                self.Kind.STORE: "Store purchase approved",
                self.Kind.AWARD: "New parent reward",
                self.Kind.BEHAVIOR: "Token balance updated",
                self.Kind.BALANCE: "Wallet balance updated",
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
                Wallet.objects.filter(pk=wallet.pk).update(spending_cents=F("spending_cents") - request.spending_delta_cents)
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

    recipient = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    title = models.CharField(max_length=80)
    message = models.CharField(max_length=240)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


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
