from django import forms

from .models import Chore, Grade, GrowthGoal, StoreItem


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
        fields = ["name", "description", "token_cost"]


class ConvertForm(forms.Form):
    cash_amount = forms.DecimalField(label="Amount to convert ($)", min_value=0.10, decimal_places=2)

    def clean_cash_amount(self):
        amount = self.cleaned_data["cash_amount"]
        if (amount * 100) % 10:
            raise forms.ValidationError("Enter an amount in 10 cent increments.")
        return amount


class CashOutForm(forms.Form):
    cash_amount = forms.DecimalField(label="Amount to cash out ($)", min_value=0.01, decimal_places=2)


class AwardForm(forms.Form):
    reason = forms.CharField(max_length=100)
    tokens = forms.IntegerField(min_value=0, initial=0)
    cash_amount = forms.DecimalField(label="Cash ($)", min_value=0, decimal_places=2, initial=0)
