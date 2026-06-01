import re
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from django import forms
from django.utils import timezone

from .models import (
    ChildRule,
    Chore,
    CommunicationSchedule,
    DailyScheduleEvent,
    DiscoverSchedule,
    FamilySettings,
    FamilyMessage,
    Grade,
    GrowthGoal,
    HouseRule,
    Profile,
    SavingsGoal,
    ShoppingProduct,
    StoreItem,
    VideoPlaylist,
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


class ShoppingProductForm(forms.ModelForm):
    retail_price = forms.DecimalField(label="Displayed retail price ($)", min_value=0.01, decimal_places=2)

    class Meta:
        model = ShoppingProduct
        fields = [
            "name",
            "description",
            "retailer",
            "retailer_url",
            "category",
            "minimum_age",
            "featured",
            "in_stock",
            "active",
        ]
        labels = {
            "retailer_url": "Purchase or Google Shopping link",
            "minimum_age": "Minimum age (optional)",
            "featured": "Featured for children",
            "in_stock": "Available to request",
            "active": "Visible in Shopping",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial.setdefault("retail_price", self.instance.retail_price_cents / 100)

    def save(self, commit=True):
        product = super().save(commit=False)
        product.retail_price_cents = int(self.cleaned_data["retail_price"] * 100)
        if commit:
            product.save()
        return product


class ShoppingFulfillmentForm(forms.Form):
    final_amount = forms.DecimalField(label="Confirmed purchase total ($)", min_value=0.01, decimal_places=2)
    parent_note = forms.CharField(label="Update for child (optional)", max_length=240, required=False)


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


class FamilyCallSettingsForm(forms.ModelForm):
    class Meta:
        model = FamilySettings
        fields = ["free_child_calls_anytime_enabled", "free_calls_after_6pm_enabled"]
        labels = {
            "free_child_calls_anytime_enabled": "Make child calls free anytime",
            "free_calls_after_6pm_enabled": "Make child calls free after 6:00 PM",
        }


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
    MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
    ATTACHMENT_RULES = {
        "photo": {
            "mime_prefixes": ("image/",),
            "mime_types": {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"},
            "extensions": {"jpg", "jpeg", "png", "webp", "heic", "heif"},
        },
        "gif": {
            "mime_prefixes": tuple(),
            "mime_types": {"image/gif"},
            "extensions": {"gif"},
        },
        "video": {
            "mime_prefixes": ("video/",),
            "mime_types": {"application/octet-stream"},
            "extensions": {"mp4", "mov", "m4v", "webm", "mpeg", "mpg", "3gp", "quicktime"},
        },
        "audio": {
            "mime_prefixes": ("audio/",),
            "mime_types": {"application/octet-stream"},
            "extensions": {"m4a", "aac", "mp3", "wav", "ogg", "webm", "mp4"},
        },
    }

    class Meta:
        model = FamilyMessage
        fields = ["body", "attachment", "gif_url"]
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 1,
                    "maxlength": 1000,
                    "placeholder": "iMessage",
                    "aria-label": "Message",
                }
            ),
            "attachment": forms.ClearableFileInput(
                attrs={
                    "accept": "image/*,video/*,audio/*",
                }
            ),
            "gif_url": forms.URLInput(
                attrs={
                    "placeholder": "Paste a GIF link",
                    "inputmode": "url",
                    "autocomplete": "off",
                }
            ),
        }

    def clean_body(self):
        body = (self.cleaned_data.get("body") or "").strip()
        return body

    def clean(self):
        cleaned = super().clean()
        body = cleaned.get("body") or ""
        attachment = cleaned.get("attachment")
        gif_url = self._normalize_gif_url(cleaned.get("gif_url") or "")
        cleaned["gif_url"] = gif_url
        if attachment and gif_url:
            raise forms.ValidationError("Choose a file or a GIF link, not both in the same message.")
        if not body and not attachment and not gif_url:
            raise forms.ValidationError("Write a message or choose a photo, GIF, video, or audio recording.")
        if attachment:
            cleaned["attachment_kind"] = self._detect_attachment_kind(attachment)
            cleaned["attachment_name"] = attachment.name[:120]
            cleaned["attachment_mime"] = (getattr(attachment, "content_type", "") or "").lower()[:80]
            self.instance.attachment_kind = cleaned["attachment_kind"]
            self.instance.attachment_name = cleaned["attachment_name"]
            self.instance.attachment_mime = cleaned["attachment_mime"]
            self.instance.gif_url = ""
        elif gif_url:
            cleaned["attachment_kind"] = FamilyMessage.AttachmentKind.GIF
            cleaned["attachment_name"] = "GIF"
            cleaned["attachment_mime"] = "image/gif"
            self.instance.attachment_kind = cleaned["attachment_kind"]
            self.instance.attachment_name = cleaned["attachment_name"]
            self.instance.attachment_mime = cleaned["attachment_mime"]
            self.instance.gif_url = gif_url
        else:
            self.instance.attachment_kind = ""
            self.instance.attachment_name = ""
            self.instance.attachment_mime = ""
            self.instance.gif_url = ""
        return cleaned

    def save(self, commit=True):
        message = super().save(commit=False)
        attachment = self.cleaned_data.get("attachment")
        if attachment:
            message.attachment_kind = self.cleaned_data["attachment_kind"]
            message.attachment_name = self.cleaned_data["attachment_name"]
            message.attachment_mime = self.cleaned_data["attachment_mime"]
            message.gif_url = ""
        elif self.cleaned_data.get("gif_url"):
            message.attachment_kind = self.cleaned_data["attachment_kind"]
            message.attachment_name = self.cleaned_data["attachment_name"]
            message.attachment_mime = self.cleaned_data["attachment_mime"]
            message.gif_url = self.cleaned_data["gif_url"]
        else:
            message.attachment_kind = ""
            message.attachment_name = ""
            message.attachment_mime = ""
            message.gif_url = ""
        if commit:
            message.save()
        return message

    def _detect_attachment_kind(self, attachment):
        content_type = (getattr(attachment, "content_type", "") or "").lower()
        extension = Path(attachment.name).suffix.lower().lstrip(".")
        if getattr(attachment, "size", 0) > self.MAX_ATTACHMENT_BYTES:
            raise forms.ValidationError("Attachments must be 25 MB or smaller.")
        for kind, rule in self.ATTACHMENT_RULES.items():
            if content_type in rule["mime_types"] or extension in rule["extensions"]:
                return kind
            if any(content_type.startswith(prefix) for prefix in rule["mime_prefixes"]):
                if kind == "photo" and extension == "gif":
                    continue
                return kind
        raise forms.ValidationError("Choose a photo, GIF, video, or audio recording supported by your device.")

    def _normalize_gif_url(self, raw_url):
        url = (raw_url or "").strip()
        if not url:
            return ""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise forms.ValidationError("Paste a full GIF link starting with http:// or https://.")
        hostname = (parsed.hostname or "").lower().removeprefix("www.")
        path = parsed.path
        if path.lower().endswith(".gif"):
            return url
        if hostname == "giphy.com":
            slug = path.rstrip("/").split("/")[-1]
            giphy_id = slug.rsplit("-", 1)[-1] if slug else ""
            if giphy_id:
                return f"https://media.giphy.com/media/{giphy_id}/giphy.gif"
        if hostname in {"media.giphy.com", "i.giphy.com"}:
            return url
        raise forms.ValidationError("Paste a direct GIF image link or a public Giphy share link.")


class ProfilePhotoForm(forms.ModelForm):
    MAX_PHOTO_BYTES = 6 * 1024 * 1024
    PHOTO_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
    PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic", "heif"}

    class Meta:
        model = Profile
        fields = ["profile_photo"]
        widgets = {
            "profile_photo": forms.FileInput(
                attrs={
                    "accept": "image/*",
                    "data-profile-photo-input": "yes",
                    "aria-label": "Choose profile photo",
                }
            )
        }

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if not photo:
            return photo
        extension = Path(photo.name).suffix.lower().lstrip(".")
        content_type = (getattr(photo, "content_type", "") or "").lower()
        if getattr(photo, "size", 0) > self.MAX_PHOTO_BYTES:
            raise forms.ValidationError("Profile photos must be 6 MB or smaller.")
        if content_type not in self.PHOTO_MIME_TYPES and extension not in self.PHOTO_EXTENSIONS:
            raise forms.ValidationError("Choose a JPG, PNG, WebP, HEIC, or HEIF photo.")
        return photo


class CommunicationScheduleForm(forms.ModelForm):
    days = forms.MultipleChoiceField(
        choices=CommunicationSchedule.WEEKDAYS,
        widget=forms.CheckboxSelectMultiple,
        label="Lock on these days",
    )

    class Meta:
        model = CommunicationSchedule
        fields = ["feature", "start_time", "end_time", "enabled"]
        labels = {
            "feature": "Lock access to",
            "start_time": "Starts at",
            "end_time": "Ends at",
            "enabled": "Schedule enabled",
        }
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["days"] = self.instance.days_of_week.split(",")
        elif not self.is_bound:
            self.initial["days"] = [value for value, _ in CommunicationSchedule.WEEKDAYS]

    def save(self, commit=True):
        schedule = super().save(commit=False)
        schedule.days_of_week = ",".join(self.cleaned_data["days"])
        if commit:
            schedule.save()
        return schedule

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("start_time") and cleaned.get("end_time") and cleaned["start_time"] == cleaned["end_time"]:
            raise forms.ValidationError("Choose different start and end times for this lock schedule.")
        return cleaned


class VideoPlaylistForm(forms.ModelForm):
    youtube_playlist_id = forms.CharField(
        label="YouTube playlist URL or ID (optional)",
        max_length=500,
        required=False,
    )

    class Meta:
        model = VideoPlaylist
        fields = ["title", "description", "youtube_playlist_id", "active"]
        labels = {
            "title": "Playlist name",
            "description": "Description (optional)",
            "active": "Available to every child",
        }

    def clean_youtube_playlist_id(self):
        source = (self.cleaned_data.get("youtube_playlist_id") or "").strip()
        if not source:
            return ""
        candidate = source
        if "://" in source:
            parsed = urlparse(source)
            host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
            if host not in {"youtube.com", "music.youtube.com", "youtube-nocookie.com"}:
                raise forms.ValidationError("Paste a public YouTube playlist link or playlist ID.")
            candidate = parse_qs(parsed.query).get("list", [""])[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,100}", candidate or ""):
            raise forms.ValidationError("Paste a public YouTube playlist link or playlist ID.")
        return candidate


class VideoClipForm(forms.Form):
    youtube_url = forms.URLField(label="YouTube video or Shorts link")
    title = forms.CharField(label="Video title", max_length=120)
    subject_tag = forms.CharField(label="Learning tag (optional)", max_length=40, required=False)


class DiscoverScheduleForm(forms.ModelForm):
    days = forms.MultipleChoiceField(
        choices=DiscoverSchedule.WEEKDAYS,
        widget=forms.CheckboxSelectMultiple,
        label="Lock Discover on these days",
    )

    class Meta:
        model = DiscoverSchedule
        fields = ["start_time", "end_time", "enabled"]
        labels = {
            "start_time": "Starts at",
            "end_time": "Ends at",
            "enabled": "Schedule enabled",
        }
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["days"] = self.instance.days_of_week.split(",")
        elif not self.is_bound:
            self.initial["days"] = [value for value, _ in DiscoverSchedule.WEEKDAYS]

    def save(self, commit=True):
        schedule = super().save(commit=False)
        schedule.days_of_week = ",".join(self.cleaned_data["days"])
        if commit:
            schedule.save()
        return schedule

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("start_time") and cleaned.get("end_time") and cleaned["start_time"] == cleaned["end_time"]:
            raise forms.ValidationError("Choose different start and end times for this Discover lock schedule.")
        return cleaned


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
