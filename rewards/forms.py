from django import forms

from django.utils import timezone

from .models import ChildRule, Chore, DailyScheduleEvent, Grade, GrowthGoal, HouseRule, SavingsGoal, StoreItem


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


class ConvertForm(forms.Form):
    cash_amount = forms.DecimalField(label="Amount to convert ($)", min_value=0.10, decimal_places=2)

    def clean_cash_amount(self):
        amount = self.cleaned_data["cash_amount"]
        if (amount * 100) % 10:
            raise forms.ValidationError("Enter an amount in 10 cent increments.")
        return amount


class CashOutForm(forms.Form):
    cash_amount = forms.DecimalField(label="Request from savings ($)", min_value=0.01, decimal_places=2)


class SpendingTransferForm(forms.Form):
    cash_amount = forms.DecimalField(label="Move to spending ($)", min_value=0.01, decimal_places=2)


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


class BalanceAdjustmentForm(forms.Form):
    SAVINGS = "savings"
    SPENDING = "spending"
    ADD = "add"
    REMOVE = "remove"

    account = forms.ChoiceField(choices=[(SAVINGS, "Savings"), (SPENDING, "Spending")])
    direction = forms.ChoiceField(choices=[(ADD, "Add money"), (REMOVE, "Remove money")])
    cash_amount = forms.DecimalField(label="Amount ($)", min_value=0.01, decimal_places=2)
    reason = forms.CharField(max_length=100, label="Reason")
