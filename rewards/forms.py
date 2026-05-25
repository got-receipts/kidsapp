from django import forms

from datetime import timedelta

from django.utils import timezone

from .models import (
    ChildRule,
    Chore,
    DailyScheduleEvent,
    FamilySettings,
    FamilyMessage,
    Grade,
    GrowthGoal,
    HouseRule,
    Profile,
    SavingsGoal,
    StoreItem,
)


class GradeForm(forms.ModelForm):
    class Meta:
        model = Grade
        fields = ["subject", "assignment", "score", "maximum_score"]


class ChildProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["birth_date"]
        labels = {"birth_date": "Birth date for age-restricted store items (optional)"}
        widgets = {"birth_date": forms.DateInput(attrs={"type": "date"})}


class ChoreForm(forms.ModelForm):
    class Meta:
        model = Chore
        fields = ["title", "instructions", "token_reward"]
        labels = {"token_reward": "Token reward"}


class GoalForm(forms.ModelForm):
    class Meta:
        model = GrowthGoal
        fields = ["title", "encouragement", "token_reward"]


class StoreItemForm(forms.ModelForm):
    cash_price = forms.DecimalField(label="Cash price ($)", min_value=0, decimal_places=2, initial=0, required=False)

    class Meta:
        model = StoreItem
        fields = [
            "name",
            "description",
            "token_cost",
            "category",
            "inventory_quantity",
            "hidden",
            "token_unlock_threshold",
            "minimum_age",
            "requires_approval",
        ]
        labels = {
            "token_cost": "Token price",
            "inventory_quantity": "Inventory quantity (blank means unlimited)",
            "hidden": "Hidden until enabled",
            "token_unlock_threshold": "Unlock after child has this many tokens",
            "minimum_age": "Minimum age (optional)",
            "requires_approval": "Require parent approval",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial.setdefault("cash_price", self.instance.cash_cost_cents / 100)

    def clean(self):
        cleaned = super().clean()
        token_cost = cleaned.get("token_cost") or 0
        cash_price = cleaned.get("cash_price") or 0
        if not token_cost and not cash_price:
            raise forms.ValidationError("Set a token price, a cash price, or both.")
        return cleaned

    def save(self, commit=True):
        item = super().save(commit=False)
        item.cash_cost_cents = int((self.cleaned_data.get("cash_price") or 0) * 100)
        if commit:
            item.save()
        return item


class DailyScheduleEventForm(forms.ModelForm):
    class Meta:
        model = DailyScheduleEvent
        fields = ["day", "start_time", "title", "details"]
        labels = {"day": "Schedule date", "start_time": "Time (optional)", "details": "Notes (optional)"}
        widgets = {
            "day": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial["day"] = timezone.localdate() + timedelta(days=1)

    def clean_day(self):
        day = self.cleaned_data["day"]
        if day < timezone.localdate():
            raise forms.ValidationError("Schedule events cannot be added to a past date.")
        return day


class ChildRuleForm(forms.ModelForm):
    class Meta:
        model = ChildRule
        fields = ["title", "details", "consequence", "expires_on", "scheduled_remove_at"]
        labels = {
            "title": "Rule",
            "details": "Details (optional)",
            "consequence": "Consequence (optional)",
            "expires_on": "Expiration date (optional)",
            "scheduled_remove_at": "Scheduled removal time (optional)",
        }
        widgets = {
            "expires_on": forms.DateInput(attrs={"type": "date"}),
            "scheduled_remove_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def clean_scheduled_remove_at(self):
        removal = self.cleaned_data.get("scheduled_remove_at")
        if removal and removal <= timezone.now():
            raise forms.ValidationError("Scheduled removal time must be in the future.")
        return removal


class HouseRuleForm(forms.ModelForm):
    class Meta:
        model = HouseRule
        fields = ["title", "details", "consequence"]
        labels = {"title": "House rule", "details": "Details (optional)", "consequence": "Consequence (optional)"}


class FamilySettingsForm(forms.ModelForm):
    class Meta:
        model = FamilySettings
        fields = ["tokens_per_dollar"]
        labels = {"tokens_per_dollar": "Tokens equal to $1.00"}


class GroundingForm(forms.Form):
    reason = forms.CharField(max_length=180, required=False, label="Message for the child (optional)")
    lift_at = forms.DateTimeField(
        required=False,
        label="Scheduled lift date and time (optional)",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )

    def clean_lift_at(self):
        lift_at = self.cleaned_data.get("lift_at")
        if lift_at and lift_at <= timezone.now():
            raise forms.ValidationError("Scheduled lift time must be in the future.")
        return lift_at


class FamilyMessageForm(forms.ModelForm):
    class Meta:
        model = FamilyMessage
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 1,
                    "maxlength": 1000,
                    "placeholder": "iMessage",
                    "aria-label": "Message",
                }
            )
        }

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if not body:
            raise forms.ValidationError("Write a message before sending.")
        return body


class TokenCashoutForm(forms.Form):
    tokens = forms.IntegerField(label="Tokens to exchange", min_value=1)
    note = forms.CharField(label="Note for parent (optional)", max_length=100, required=False)


class TokenGiftForm(forms.Form):
    recipient_id = forms.ModelChoiceField(queryset=Profile.objects.none(), label="Send tokens to")
    tokens = forms.IntegerField(label="Tokens to send", min_value=1)

    def __init__(self, *args, sender=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Profile.objects.filter(role=Profile.Role.CHILD)
        if sender is not None:
            queryset = queryset.exclude(pk=sender.pk)
        self.fields["recipient_id"].queryset = queryset.order_by("display_name")


class SpendingTransferForm(forms.Form):
    cash_amount = forms.DecimalField(label="Amount ($)", min_value=0.01, decimal_places=2)


class FamilyTransferForm(forms.Form):
    recipient_id = forms.ModelChoiceField(queryset=Profile.objects.none(), label="Send to")
    cash_amount = forms.DecimalField(label="Amount to send ($)", min_value=0.01, decimal_places=2)

    def __init__(self, *args, sender=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Profile.objects.filter(role=Profile.Role.CHILD)
        if sender is not None:
            queryset = queryset.exclude(pk=sender.pk)
        self.fields["recipient_id"].queryset = queryset.order_by("display_name")


class SavingsGoalForm(forms.ModelForm):
    target_amount = forms.DecimalField(label="How much do you want to save? ($)", min_value=0.01, decimal_places=2)

    class Meta:
        model = SavingsGoal
        fields = ["name"]
        labels = {"name": "What are you saving for?"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and "target_amount" not in self.initial:
            self.initial["target_amount"] = self.instance.target_cents / 100


class AwardForm(forms.Form):
    reason = forms.CharField(max_length=100, label="Reward note")
    tokens = forms.IntegerField(min_value=0, initial=0, label="Bonus tokens")
    cash_amount = forms.DecimalField(label="Direct wallet cash ($)", min_value=0, decimal_places=2, initial=0)


class BehaviorDeductionForm(forms.Form):
    reason = forms.CharField(max_length=100, label="What happened?")
    tokens = forms.IntegerField(min_value=1, label="Tokens to remove")


class BalanceAdjustmentForm(forms.Form):
    SAVINGS = "savings"
    SPENDING = "spending"
    ADD = "add"
    REMOVE = "remove"

    account = forms.ChoiceField(choices=[(SAVINGS, "Cash App balance")])
    direction = forms.ChoiceField(choices=[(ADD, "Add money"), (REMOVE, "Remove money")])
    cash_amount = forms.DecimalField(label="Amount ($)", min_value=0.01, decimal_places=2)
    reason = forms.CharField(max_length=100, label="Reason")
