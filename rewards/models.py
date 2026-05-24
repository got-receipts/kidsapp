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

    def __str__(self):
        return self.display_name

    @property
    def is_guardian(self):
        return self.role == self.Role.GUARDIAN


class Wallet(models.Model):
    child = models.OneToOneField(Profile, on_delete=models.CASCADE, related_name="wallet")
    tokens = models.PositiveIntegerField(default=0)
    cash_cents = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.child.display_name}'s wallet"


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

    child = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="chores")
    title = models.CharField(max_length=100)
    instructions = models.CharField(max_length=240, blank=True)
    token_reward = models.PositiveIntegerField(default=0)
    cash_reward_cents = models.PositiveIntegerField(default=0)
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
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=180, blank=True)
    token_cost = models.PositiveIntegerField()
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
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    chore = models.OneToOneField(Chore, null=True, blank=True, on_delete=models.SET_NULL)
    goal = models.OneToOneField(GrowthGoal, null=True, blank=True, on_delete=models.SET_NULL)
    behavior_star = models.OneToOneField(BehaviorStar, null=True, blank=True, on_delete=models.SET_NULL)
    store_item = models.ForeignKey(StoreItem, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def approve(self, guardian):
        from django.utils import timezone

        if not guardian.is_guardian:
            raise ValidationError("Only guardians can approve requests.")
        with transaction.atomic():
            request = LedgerRequest.objects.select_for_update().get(pk=self.pk)
            if request.status != self.Status.PENDING:
                return
            wallet = Wallet.objects.select_for_update().get(child=request.child)
            if wallet.tokens + request.token_delta < 0:
                raise ValidationError("Not enough tokens for this request.")
            if wallet.cash_cents + request.cash_delta_cents < 0:
                raise ValidationError("Not enough cash balance for this request.")
            Wallet.objects.filter(pk=wallet.pk).update(
                tokens=F("tokens") + request.token_delta,
                cash_cents=F("cash_cents") + request.cash_delta_cents,
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
                request.chore.status = Chore.Status.OPEN
                request.chore.save(update_fields=["status"])
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
