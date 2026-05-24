from datetime import time

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F


class Profile(models.Model):
    class Role(models.TextChoices):
        CHILD = "child", "Child"
        GUARDIAN = "guardian", "Guardian"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=40)
    role = models.CharField(max_length=10, choices=Role.choices)
    last_recap_at = models.DateTimeField(null=True, blank=True)
    last_recap_day = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.display_name

    @property
    def is_guardian(self):
        return self.role == self.Role.GUARDIAN


class Wallet(models.Model):
    child = models.OneToOneField(Profile, on_delete=models.CASCADE, related_name="wallet")
    tokens = models.IntegerField(default=0)
    cash_cents = models.PositiveIntegerField(default=0)
    spending_cents = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.child.display_name}'s wallet"


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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["day", "start_time", "created_at"]

    def __str__(self):
        return f"{self.child.display_name}: {self.title}"


class ChildRule(models.Model):
    child = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="specific_rules")
    title = models.CharField(max_length=100)
    details = models.CharField(max_length=240, blank=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="child_rules_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.child.display_name}: {self.title}"


class HouseRule(models.Model):
    title = models.CharField(max_length=100)
    details = models.CharField(max_length=240, blank=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="house_rules_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.title


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
            models.UniqueConstraint(fields=["child", "title", "due_date"], name="one_daily_chore_assignment")
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
    token_cost = models.PositiveIntegerField()
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.TREAT)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


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
        CONVERT = "convert", "Cash to tokens"
        CASH_OUT = "cash_out", "Cash out"
        AWARD = "award", "Guardian award"
        STAR = "star", "Good behavior star"
        TRANSFER = "transfer", "Move to spending"
        BALANCE = "balance", "Balance correction"
        PENALTY = "penalty", "Quest not verified"
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
        return self.kind in [self.Kind.TRANSFER, self.Kind.CASH_OUT, self.Kind.CONVERT]

    def approve(self, guardian):
        from django.utils import timezone

        if not guardian.is_guardian:
            raise ValidationError("Only guardians can approve requests.")
        if self.requires_dad_approval and guardian.user.username.lower() != "dad":
            raise ValidationError("Only Dad can approve savings and spending requests.")
        with transaction.atomic():
            request = LedgerRequest.objects.select_for_update().get(pk=self.pk)
            if request.status != self.Status.PENDING:
                return
            wallet = Wallet.objects.select_for_update().get(child=request.child)
            if request.kind != self.Kind.PENALTY and wallet.tokens + request.token_delta < 0:
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

    def decline(self, guardian):
        from django.utils import timezone

        if not guardian.is_guardian:
            raise ValidationError("Only guardians can decline requests.")
        with transaction.atomic():
            request = LedgerRequest.objects.select_for_update().get(pk=self.pk)
            if request.status != self.Status.PENDING:
                return
            request.status = self.Status.DECLINED
            request.reviewed_by = guardian
            request.reviewed_at = timezone.now()
            request.save(update_fields=["status", "reviewed_by", "reviewed_at"])
            if request.chore:
                request.chore.status = Chore.Status.NOT_VERIFIED
                request.chore.save(update_fields=["status"])
                if request.chore.token_reward:
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
