from django import forms

from django.utils import timezone

from .models import ChildRule, Chore, DailyScheduleEvent, FamilySettings, Grade, GrowthGoal, HouseRule, Profile, SavingsGoal, StoreItem


class GradeForm(forms.ModelForm):
    class Meta:
        model = Grade
        fields = ["subject", "assignment", "score", "maximum_score"]


class ChoreForm(forms.ModelForm):
    cash_reward = forms.DecimalField(label="Cash reward ($)", min_value=0, decimal_places=2, initial=0)

    class Meta:
        model = Chore
        fields = ["title", "instructions", "token_reward"]


class GoalForm(forms.ModelForm):
    class Meta:
        model = GrowthGoal
        fields = ["title", "encouragement", "token_reward"]


class StoreItemForm(forms.ModelForm):
    class Meta:
        model = StoreItem
        fields = ["name", "description", "token_cost", "category"]


class DailyScheduleEventForm(forms.ModelForm):
    class Meta:
        model = DailyScheduleEvent
        fields = ["day", "start_time", "title", "details"]
        labels = {"day": "Date", "start_time": "Time (optional)", "details": "Notes (optional)"}
        widgets = {
            "day": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial["day"] = timezone.localdate()


class ChildRuleForm(forms.ModelForm):
    class Meta:
        model = ChildRule
        fields = ["title", "details"]
        labels = {"title": "Rule", "details": "Why or reminder (optional)"}


class HouseRuleForm(forms.ModelForm):
    class Meta:
        model = HouseRule
        fields = ["title", "details"]
        labels = {"title": "House rule", "details": "Why or reminder (optional)"}


class GroundingForm(forms.Form):
    reason = forms.CharField(max_length=180, required=False, label="Message for the child (optional)")


class GoogleCalendarSettingsForm(forms.ModelForm):
    class Meta:
        model = FamilySettings
        fields = ["google_calendar_enabled", "google_calendar_id"]
        labels = {
            "google_calendar_enabled": "Show public Google Calendar events",
            "google_calendar_id": "Public Google Calendar ID",
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("google_calendar_enabled") and not cleaned.get("google_calendar_id", "").strip():
            self.add_error("google_calendar_id", "Enter a calendar ID before turning this on.")
        return cleaned


class ConvertForm(forms.Form):
    cash_amount = forms.DecimalField(label="Amount to convert ($)", min_value=0.10, decimal_places=2)

    def clean_cash_amount(self):
        amount = self.cleaned_data["cash_amount"]
        if (amount * 100) % 10:
            raise forms.ValidationError("Enter an amount in 10 cent increments.")
        return amount


class TokensToSavingsForm(forms.Form):
    cash_amount = forms.DecimalField(label="Savings amount to receive ($)", min_value=0.10, decimal_places=2)

    def clean_cash_amount(self):
        amount = self.cleaned_data["cash_amount"]
        if (amount * 100) % 10:
            raise forms.ValidationError("Enter an amount in 10 cent increments.")
        return amount


class CashOutForm(forms.Form):
    cash_amount = forms.DecimalField(label="Request from savings ($)", min_value=0.01, decimal_places=2)


class SpendingTransferForm(forms.Form):
    cash_amount = forms.DecimalField(label="Move to spending ($)", min_value=0.01, decimal_places=2)


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
    reason = forms.CharField(max_length=100)
    tokens = forms.IntegerField(min_value=0, initial=0)
    cash_amount = forms.DecimalField(label="Cash ($)", min_value=0, decimal_places=2, initial=0)


class BehaviorDeductionForm(forms.Form):
    reason = forms.CharField(max_length=100, label="What happened?")
    tokens = forms.IntegerField(min_value=1, label="Tokens to remove")


class BalanceAdjustmentForm(forms.Form):
    SAVINGS = "savings"
    SPENDING = "spending"
    ADD = "add"
    REMOVE = "remove"

    account = forms.ChoiceField(choices=[(SAVINGS, "Savings"), (SPENDING, "Spending")])
    direction = forms.ChoiceField(choices=[(ADD, "Add money"), (REMOVE, "Remove money")])
    cash_amount = forms.DecimalField(label="Amount ($)", min_value=0.01, decimal_places=2)
    reason = forms.CharField(max_length=100, label="Reason")
