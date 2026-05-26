import calendar
import json
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, quote, urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, F, IntegerField, Max, Q, Sum, When
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .forms import (
    AwardForm,
    BalanceAdjustmentForm,
    BehaviorDeductionForm,
    ChildProfileForm,
    ChildRuleForm,
    ChoreForm,
    CommunicationScheduleForm,
    DailyScheduleEventForm,
    DiscoverScheduleForm,
    FamilyMessageForm,
    FamilySettingsForm,
    GoalForm,
    GradeForm,
    GroundingForm,
    HouseRuleForm,
    SavingsGoalForm,
    ShoppingFulfillmentForm,
    ShoppingProductForm,
    SpendingTransferForm,
    StoreItemForm,
    TokenCashoutForm,
    TokenGiftForm,
    VideoClipForm,
    VideoPlaylistForm,
    FamilyTransferForm,
)
from .models import (
    AuditLog,
    BehaviorNote,
    BehaviorStar,
    ChildRule,
    Chore,
    CommunicationSchedule,
    DailyScheduleEvent,
    DiscoverSchedule,
    FamilyMessage,
    FamilyCall,
    FamilySettings,
    GrowthGoal,
    HouseRule,
    LedgerRequest,
    Notification,
    Profile,
    Purchase,
    PushSubscription,
    RuleAcknowledgement,
    SavingsGoal,
    ShoppingCartItem,
    ShoppingOrder,
    ShoppingOrderItem,
    ShoppingProduct,
    StoreItem,
    VideoClip,
    VideoFavorite,
    VideoPlaylist,
    VideoPlaylistAssignment,
    VideoWatchEvent,
    Wallet,
)
from .services import ensure_today_chores


CHILD_SECTIONS = {"today", "chores", "badges", "school", "store", "savings", "goals"}


class FamilyLoginView(LoginView):
    template_name = "rewards/login.html"
    redirect_authenticated_user = True


def health(request):
    return HttpResponse("ok", content_type="text/plain")


def csrf_failure(request, reason=""):
    return render(request, "rewards/csrf_failure.html", status=403)


def service_worker(request):
    source = """const CACHE = 'family-circle-v7';
const CORE = ['/static/rewards/styles.css', '/static/rewards/app.js', '/static/rewards/icon.svg', '/static/rewards/icon-192.png', '/static/rewards/icon-512.png', '/static/rewards/apple-touch-icon.png', '/static/rewards/catalog/building.svg', '/static/rewards/catalog/stem.svg', '/static/rewards/catalog/creative.svg', '/static/rewards/catalog/games.svg', '/static/rewards/catalog/outdoor.svg', '/static/rewards/catalog/electronics.svg', '/static/rewards/catalog/pretend.svg', '/static/rewards/catalog/gift.svg'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(CORE))); self.skipWaiting(); });
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('push', event => {
  const data = event.data ? event.data.json() : {title: 'Family Circle', body: 'Open Family Circle for an update.'};
  event.waitUntil(Promise.all([
    self.registration.showNotification(data.title, {body: data.body, icon: '/static/rewards/icon-192.png', badge: '/static/rewards/icon-192.png', data: {url: data.url || '/'}}),
    self.navigator.setAppBadge ? self.navigator.setAppBadge(1) : Promise.resolve()
  ]));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(Promise.all([
    self.clients.openWindow(event.notification.data.url || '/'),
    self.navigator.clearAppBadge ? self.navigator.clearAppBadge() : Promise.resolve()
  ]));
});
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  if (!new URL(event.request.url).pathname.startsWith('/static/')) return;
  event.respondWith(fetch(event.request).then(response => {
    if (response.ok && event.request.url.startsWith(self.location.origin)) {
      caches.open(CACHE).then(cache => cache.put(event.request, response.clone()));
    }
    return response;
  }).catch(() => caches.match(event.request)));
});"""
    return HttpResponse(source, content_type="application/javascript", headers={"Service-Worker-Allowed": "/"})


def _profile(request):
    profile = get_object_or_404(Profile, user=request.user)
    profile.refresh_grounding()
    return profile


def _guardian(request):
    profile = _profile(request)
    if not profile.is_guardian:
        messages.error(request, "Your account can view family progress, but only Dad or GG can make changes.")
        return None
    return profile


def _dad(request):
    guardian = _guardian(request)
    if guardian is None:
        return None
    if guardian.user.username.lower() != "dad":
        messages.error(request, "Only Dad can complete this action.")
        return None
    return guardian


def _fulfiller(request):
    profile = _profile(request)
    if profile.is_guardian or (profile.role == Profile.Role.VIEWER and profile.user.username.lower() == "mom"):
        return profile
    messages.error(request, "Only Mom, Dad, or GG can manage shopping fulfillment.")
    return None


def _video_manager(request):
    profile = _profile(request)
    if profile.is_guardian or (profile.role == Profile.Role.VIEWER and profile.user.username.lower() == "mom"):
        return profile
    messages.error(request, "Only Mom, Dad, or GG can manage Discover videos.")
    return None


def _block_grounded_child(request, profile):
    if profile.role == Profile.Role.CHILD and profile.grounded:
        messages.error(request, "Grounded Mode is active. Money, tokens, rewards, and the store are locked.")
        return True
    return False


def _child_destination(request, default="dashboard"):
    section = request.POST.get("return_section")
    if section in CHILD_SECTIONS:
        return redirect("child_section", section=section)
    return redirect(default)


def _cents(amount):
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


def _cash_for_tokens(tokens, family_settings):
    return int((Decimal(tokens) * Decimal("100") / family_settings.tokens_per_dollar).quantize(Decimal("1")))


def _cash_sources(wallet, cents):
    wallet_cash = min(wallet.cash_cents, cents)
    legacy_cash = cents - wallet_cash
    if legacy_cash > wallet.spending_cents:
        return None
    return wallet_cash, legacy_cash


def _notify(child, kind, title, message):
    if child.role == Profile.Role.CHILD:
        Notification.objects.create(recipient=child, kind=kind, title=title, message=message[:240])


def _audit(actor, child, action, description, **related):
    AuditLog.objects.create(actor=actor, child=child, action=action, description=description[:240], **related)


def _shopping_photo_fallback(category):
    safe_category = category if category in ShoppingProduct.Category.values else "gift"
    return redirect(static(f"rewards/catalog/{safe_category}.svg"))


def _message_query(profile, contact):
    return Q(sender=profile, recipient=contact) | Q(sender=contact, recipient=profile)


def _unread_message_count(profile):
    return profile.received_family_messages.filter(read_at__isnull=True).count()


def _message_contacts(profile):
    contacts = list(Profile.objects.exclude(pk=profile.pk).order_by("display_name"))
    for contact in contacts:
        contact.last_message = (
            FamilyMessage.objects.filter(_message_query(profile, contact))
            .select_related("sender")
            .order_by("-created_at")
            .first()
        )
        contact.unread_count = profile.received_family_messages.filter(sender=contact, read_at__isnull=True).count()
    return contacts


def _communication_lock(profile, feature):
    if profile.role != Profile.Role.CHILD:
        return None
    feature_filter = [feature, CommunicationSchedule.Feature.BOTH]
    for schedule in profile.communication_schedules.filter(enabled=True, feature__in=feature_filter):
        if schedule.applies_at():
            return schedule
    return None


def _discover_lock(profile):
    if profile.role != Profile.Role.CHILD:
        return None
    for schedule in profile.discover_schedules.filter(enabled=True):
        if schedule.applies_at():
            return schedule
    return None


def _assigned_discover_clips(profile):
    return (
        VideoClip.objects.filter(
            active=True,
            playlist__active=True,
            playlist__assignments__child=profile,
            playlist__assignments__enabled=True,
        )
        .select_related("playlist")
        .distinct()
        .order_by("playlist__title", "position", "created_at")
    )


def _assigned_discover_playlists(profile):
    return (
        VideoPlaylist.objects.filter(
            active=True,
            assignments__child=profile,
            assignments__enabled=True,
        )
        .exclude(youtube_playlist_id="")
        .distinct()
        .order_by("title")
    )


def _youtube_id(url):
    parsed = urlparse(url or "")
    hostname = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    candidate = ""
    if hostname == "youtu.be":
        candidate = parsed.path.strip("/").split("/")[0]
    elif hostname in {"youtube.com", "youtube-nocookie.com"}:
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        elif parts and parts[0] in {"shorts", "embed", "live"} and len(parts) > 1:
            candidate = parts[1]
    return candidate if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate or "") else ""


def _call_schedule_lock(call):
    for participant in (call.caller, call.recipient):
        schedule = _communication_lock(participant, CommunicationSchedule.Feature.CALLING)
        if schedule:
            return participant, schedule
    return None, None


def _livekit_configured():
    return bool(settings.LIVEKIT_WS_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET)


def _child_call_allowance(profile):
    if profile.role != Profile.Role.CHILD:
        return None
    used = FamilyCall.objects.filter(caller=profile, allowance_day=timezone.localdate()).count()
    free_limit = max(settings.FREE_CHILD_CALLS_PER_DAY, 0)
    return {
        "used": used,
        "free_limit": free_limit,
        "remaining": max(free_limit - used, 0),
        "token_cost": max(settings.CHILD_CALL_TOKEN_COST, 0),
        "reconnect_minutes": max(settings.CALL_RECONNECT_MINUTES, 1),
    }


def _incoming_call(profile):
    _expire_ringing_calls()
    cutoff = timezone.now() - timedelta(minutes=3)
    return (
        FamilyCall.objects.filter(recipient=profile, status=FamilyCall.Status.RINGING, created_at__gte=cutoff)
        .select_related("caller")
        .first()
    )


def _expire_ringing_calls():
    now = timezone.now()
    FamilyCall.objects.filter(
        status=FamilyCall.Status.RINGING,
        created_at__lt=now - timedelta(minutes=3),
    ).update(status=FamilyCall.Status.ENDED, ended_at=now)


def _make_livekit_token(profile, call):
    try:
        from livekit import api
    except ImportError as error:
        raise ValidationError("LiveKit server support is not installed.") from error
    remaining = (
        call.access_expires_at - timezone.now()
        if call.access_expires_at
        else timedelta(minutes=max(settings.CALL_RECONNECT_MINUTES, 1))
    )
    if remaining <= timedelta(0):
        raise ValidationError("The reconnect window has ended. Start a new call.")
    return (
        api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(f"profile-{profile.pk}")
        .with_name(profile.display_name)
        .with_ttl(remaining)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=call.room_name,
                can_publish=True,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )


def _expire_rules():
    now = timezone.now()
    ChildRule.objects.filter(active=True).filter(
        Q(expires_on__lt=timezone.localdate()) | Q(scheduled_remove_at__lte=now)
    ).update(active=False)


def _current_child_rules(child):
    return child.specific_rules.filter(active=True).filter(
        Q(expires_on__isnull=True) | Q(expires_on__gte=timezone.localdate()),
        Q(scheduled_remove_at__isnull=True) | Q(scheduled_remove_at__gt=timezone.now()),
    )


def _current_house_rules():
    return HouseRule.objects.filter(active=True)


def _star_streak(child):
    days = set(child.behavior_stars.values_list("day", flat=True))
    day = timezone.localdate()
    if day not in days:
        day -= timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def _wallet_context(profile):
    pending_spending = profile.ledger_requests.filter(
        kind=LedgerRequest.Kind.SPEND,
        status=LedgerRequest.Status.PENDING,
    )
    return {
        "wallet": profile.wallet,
        "cash_app_balance_cents": profile.wallet.available_cash_cents,
        "ledger": profile.ledger_requests.all()[:20],
        "pending_spending": pending_spending,
        "pending_spending_total_cents": sum(-entry.money_delta_cents for entry in pending_spending),
        "pending_wallet_actions": pending_spending,
        "family_settings": FamilySettings.load(),
        "token_cashout_form": TokenCashoutForm(),
        "token_gift_form": TokenGiftForm(sender=profile),
        "family_transfer_form": FamilyTransferForm(sender=profile),
    }


def _star_calendar(child, requested_month):
    today = timezone.localdate()
    try:
        shown = datetime.strptime(requested_month, "%Y-%m").date().replace(day=1)
    except (TypeError, ValueError):
        shown = today.replace(day=1)
    stars = set(child.behavior_stars.filter(day__year=shown.year, day__month=shown.month).values_list("day", flat=True))
    weeks = []
    for week in calendar.Calendar(firstweekday=6).monthdatescalendar(shown.year, shown.month):
        weeks.append([
            {
                "day": cell,
                "in_month": cell.month == shown.month,
                "has_star": cell in stars,
                "awardable": cell <= today and cell.month == shown.month,
            }
            for cell in week
        ])
    previous = (shown.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    next_month = (shown.replace(day=28) + timedelta(days=4)).replace(day=1).strftime("%Y-%m")
    return weeks, shown.strftime("%B %Y"), previous, next_month


def _store_catalog():
    return StoreItem.objects.filter(active=True).order_by(
        Case(
            When(category=StoreItem.Category.TREAT, then=0),
            When(category=StoreItem.Category.EXPERIENCE, then=1),
            When(category=StoreItem.Category.GRAND, then=2),
            output_field=IntegerField(),
        ),
        "token_cost",
    )


def _child_context(profile, family_settings, include_welcome=True):
    store_items = [item for item in _store_catalog() if item.available_to(profile)]
    today_chores = profile.chores.filter(due_date=timezone.localdate(), optional=False).order_by("title")
    optional_chores = profile.chores.filter(due_date=timezone.localdate(), optional=True).order_by("title")
    checked = today_chores.filter(status__in=[Chore.Status.SUBMITTED, Chore.Status.COMPLETED]).count()
    verified = today_chores.filter(status=Chore.Status.COMPLETED).count()
    not_verified = today_chores.filter(status=Chore.Status.NOT_VERIFIED).count()
    since = profile.last_recap_at
    recap_entries = profile.ledger_requests.filter(status=LedgerRequest.Status.APPROVED)
    recap_stars = profile.behavior_stars.all()
    if since:
        recap_entries = recap_entries.filter(reviewed_at__gt=since)
        recap_stars = recap_stars.filter(created_at__gt=since)
    else:
        recap_entries = recap_entries.none()
        recap_stars = recap_stars.none()
    recap_token_total = (
        recap_entries.filter(token_delta__gt=0)
        .exclude(kind=LedgerRequest.Kind.REVERSAL)
        .aggregate(total=Sum("token_delta"))["total"]
        or 0
    )
    punishment_net = (
        recap_entries.filter(
            kind__in=[LedgerRequest.Kind.PENALTY, LedgerRequest.Kind.BEHAVIOR, LedgerRequest.Kind.REVERSAL]
        ).aggregate(total=Sum("token_delta"))["total"]
        or 0
    )
    recap_token_loss = max(-punishment_net, 0)
    recap_purchases = recap_entries.filter(kind=LedgerRequest.Kind.STORE).count()
    next_prize = next((item for item in store_items if item.token_cost > profile.wallet.tokens), None)
    savings_goal = SavingsGoal.objects.filter(child=profile).first()
    today = timezone.localdate()
    specific_rules = list(_current_child_rules(profile))
    house_rules = list(_current_house_rules())
    acknowledged_house = set(
        profile.rule_acknowledgements.filter(house_rule__isnull=False).values_list("house_rule_id", flat=True)
    )
    acknowledged_personal = set(
        profile.rule_acknowledgements.filter(child_rule__isnull=False).values_list("child_rule_id", flat=True)
    )
    for rule in specific_rules:
        rule.acknowledged = rule.pk in acknowledged_personal
    for rule in house_rules:
        rule.acknowledged = rule.pk in acknowledged_house
    streak_count = _star_streak(profile)
    return {
        "profile": profile,
        "wallet": profile.wallet,
        "cash_app_balance_cents": profile.wallet.available_cash_cents,
        "grades": profile.grades.all().order_by("-created_at")[:8],
        "chores": today_chores,
        "optional_chores": optional_chores,
        "chore_total": today_chores.count(),
        "chore_completed": checked,
        "chore_percent": round(checked / today_chores.count() * 100) if today_chores.count() else 0,
        "chore_verified": verified,
        "chore_verified_percent": round(verified / today_chores.count() * 100) if today_chores.count() else 0,
        "chore_not_verified": not_verified,
        "star_count": profile.behavior_stars.count(),
        "star_today": profile.behavior_stars.filter(day=today).exists(),
        "goals": profile.goals.exclude(status=GrowthGoal.Status.COMPLETED).order_by("created_at"),
        "store_items": store_items,
        "family_settings": family_settings,
        "savings_goal": savings_goal,
        "savings_goal_form": SavingsGoalForm(instance=savings_goal),
        "today": today,
        "quest_deadline": timezone.make_aware(datetime.combine(today, time(19, 0))),
        "morning_deadline": timezone.make_aware(datetime.combine(today, time(10, 0))),
        "today_schedule": profile.schedule_events.filter(day=today, approved_at__isnull=False),
        "specific_rules": specific_rules,
        "house_rules": house_rules,
        "unread_notifications": profile.notifications.filter(read_at__isnull=True)[:10],
        "unread_message_count": _unread_message_count(profile),
        "show_recap": include_welcome and profile.last_recap_day != today,
        "recap_first_visit": since is None,
        "recap_star_count": recap_stars.count(),
        "recap_token_total": recap_token_total,
        "recap_token_loss": recap_token_loss,
        "recap_purchases": recap_purchases,
        "recap_tasks_left": today_chores.filter(status__in=[Chore.Status.OPEN, Chore.Status.IN_PROGRESS]).count(),
        "next_prize": next_prize,
        "tokens_to_next_prize": next_prize.token_cost - profile.wallet.tokens if next_prize else 0,
        "streak_count": streak_count,
        "token_badge": profile.wallet.tokens >= 50,
        "quest_badge": verified >= 3,
        "streak_badge": streak_count >= 3,
        "discover_lock": _discover_lock(profile),
    }


@login_required
def dashboard(request):
    ensure_today_chores()
    _expire_rules()
    for child in Profile.objects.filter(role=Profile.Role.CHILD, grounded=True):
        child.refresh_grounding()
    profile = _profile(request)
    family_settings = FamilySettings.load()
    store_items = _store_catalog()
    if profile.can_view_family:
        can_manage = profile.is_guardian
        dad_controls = can_manage and profile.user.username.lower() == "dad"
        can_fulfill = can_manage or (profile.role == Profile.Role.VIEWER and profile.user.username.lower() == "mom")
        can_manage_video = can_manage or (profile.role == Profile.Role.VIEWER and profile.user.username.lower() == "mom")
        children = Profile.objects.filter(role=Profile.Role.CHILD).select_related("wallet")
        selected = children.filter(pk=request.GET.get("child")).first() or children.first()
        star_weeks, star_month, previous_month, next_month = _star_calendar(selected, request.GET.get("month")) if selected else ([], "", "", "")
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        unstarred = children.exclude(behavior_stars__day=today)
        schedule_waiting = children.exclude(
            pk__in=DailyScheduleEvent.objects.filter(day=tomorrow, approved_at__isnull=False).values("child_id")
        )
        pending = LedgerRequest.objects.filter(status=LedgerRequest.Status.PENDING).select_related("child", "chore")
        family_calendar_events = (
            DailyScheduleEvent.objects.filter(day__gte=today)
            .select_related("child", "created_by", "approved_by")
            .order_by("day", "start_time", "child__display_name")[:120]
            if can_manage else []
        )
        upcoming_event_queue = (
            DailyScheduleEvent.objects.filter(day__gt=today)
            .select_related("child", "approved_by")
            .order_by("day", "start_time", "child__display_name")[:16]
            if can_manage else []
        )
        history = selected.ledger_requests.select_related("store_item", "reviewed_by", "reversal").all()[:30] if selected else []
        if selected and not can_manage:
            history = selected.ledger_requests.filter(
                status=LedgerRequest.Status.APPROVED,
            ).filter(
                Q(kind__in=[LedgerRequest.Kind.CHORE, LedgerRequest.Kind.GOAL, LedgerRequest.Kind.STAR])
                | Q(kind=LedgerRequest.Kind.AWARD, cash_delta_cents=0, spending_delta_cents=0)
            ).select_related("store_item", "reviewed_by")[:30]
        context = {
            "profile": profile,
            "can_manage": can_manage,
            "can_fulfill": can_fulfill,
            "can_manage_video": can_manage_video,
            "can_manage_catalog": dad_controls,
            "children": children,
            "selected": selected,
            "store_items": store_items,
            "pending": pending.exclude(kind__in=[LedgerRequest.Kind.CHORE, LedgerRequest.Kind.SHOPPING]),
            "pending_chore_reviews": pending.filter(child=selected, kind=LedgerRequest.Kind.CHORE) if selected else [],
            "selected_chores": selected.chores.filter(due_date=today, optional=False).order_by("title") if selected else [],
            "selected_optional_chores": selected.chores.filter(due_date=today, optional=True).order_by("title") if selected else [],
            "selected_schedule": (
                selected.schedule_events.filter(day__gte=today)[:20]
                if selected and can_manage
                else selected.schedule_events.filter(day__gte=today, approved_at__isnull=False)[:20]
                if selected else []
            ),
            "family_calendar_events": family_calendar_events,
            "upcoming_event_queue": upcoming_event_queue,
            "selected_rules": selected.specific_rules.filter(active=True) if selected else [],
            "selected_grades": selected.grades.order_by("-created_at")[:8] if selected else [],
            "selected_goals": selected.goals.order_by("-created_at")[:8] if selected else [],
            "behavior_notes": selected.behavior_notes.select_related("issued_by")[:20] if selected else [],
            "punishment_entries": (
                selected.ledger_requests.filter(
                    kind__in=[LedgerRequest.Kind.PENALTY, LedgerRequest.Kind.BEHAVIOR],
                    status=LedgerRequest.Status.APPROVED,
                ).select_related("reversal")[:20]
                if selected and can_manage else []
            ),
            "house_rules": _current_house_rules(),
            "all_house_rules": HouseRule.objects.all(),
            "all_selected_rules": selected.specific_rules.all() if selected else [],
            "all_store_items": StoreItem.objects.all().order_by("name"),
            "recent_audit": AuditLog.objects.select_related("actor", "child")[:20],
            "history": history,
            "star_weeks": star_weeks,
            "star_month": star_month,
            "previous_month": previous_month,
            "next_month": next_month,
            "unstarred": unstarred,
            "star_reminder_due": can_manage and timezone.localtime().time() >= time(19, 30) and unstarred.exists(),
            "schedule_reminder_due": dad_controls and timezone.localtime().time() >= time(21, 0) and schedule_waiting.exists(),
            "schedule_waiting": schedule_waiting,
            "tomorrow": tomorrow,
            "vapid_public_key": settings.VAPID_PUBLIC_KEY,
            "grade_form": GradeForm(),
            "child_profile_form": ChildProfileForm(instance=selected) if selected else None,
            "chore_form": ChoreForm(),
            "goal_form": GoalForm(),
            "item_form": StoreItemForm(),
            "schedule_form": DailyScheduleEventForm(),
            "child_rule_form": ChildRuleForm(),
            "house_rule_form": HouseRuleForm(),
            "settings_form": FamilySettingsForm(instance=family_settings),
            "family_settings": family_settings,
            "award_form": AwardForm(),
            "behavior_deduction_form": BehaviorDeductionForm(),
            "balance_form": BalanceAdjustmentForm(),
            "grounding_form": GroundingForm(),
            "dad_controls": dad_controls,
            "unread_message_count": _unread_message_count(profile),
            "selected_communication_schedules": selected.communication_schedules.all() if selected and can_manage else [],
            "communication_schedule_form": CommunicationScheduleForm(),
            "livekit_configured": _livekit_configured(),
            "shopping_orders": (
                ShoppingOrder.objects.select_related("child", "assigned_to", "reservation_ledger")
                .prefetch_related("items")
                .all()[:40]
                if can_fulfill else []
            ),
            "open_shopping_order_count": (
                ShoppingOrder.objects.filter(status__in=[ShoppingOrder.Status.SUBMITTED, ShoppingOrder.Status.CLAIMED]).count()
                if can_fulfill else 0
            ),
            "shopping_catalog": ShoppingProduct.objects.all() if dad_controls else [],
            "shopping_product_form": ShoppingProductForm() if dad_controls else None,
            "video_playlists": (
                VideoPlaylist.objects.prefetch_related("clips", "assignments").all()
                if can_manage_video else []
            ),
            "selected_video_playlist_ids": (
                list(
                    selected.video_playlist_assignments.filter(enabled=True).values_list("playlist_id", flat=True)
                )
                if selected and can_manage_video else []
            ),
            "selected_discover_schedules": selected.discover_schedules.all() if selected and can_manage_video else [],
            "selected_video_favorites": (
                selected.video_favorites.select_related("clip", "clip__playlist")[:10]
                if selected and can_manage_video else []
            ),
            "selected_video_watch_events": (
                selected.video_watch_events.select_related("clip", "clip__playlist")[:10]
                if selected and can_manage_video else []
            ),
            "video_playlist_form": VideoPlaylistForm() if can_manage_video else None,
            "discover_schedule_form": DiscoverScheduleForm() if can_manage_video else None,
        }
        return render(request, "rewards/guardian_dashboard.html", context)
    return render(request, "rewards/child_dashboard.html", _child_context(profile, family_settings))


@login_required
@require_http_methods(["GET"])
def messages_inbox(request):
    profile = _profile(request)
    incoming_call = None if _communication_lock(profile, CommunicationSchedule.Feature.CALLING) else _incoming_call(profile)
    return render(
        request,
        "rewards/messages_inbox.html",
        {
            "profile": profile,
            "contacts": _message_contacts(profile),
            "unread_message_count": _unread_message_count(profile),
            "messaging_lock": _communication_lock(profile, CommunicationSchedule.Feature.MESSAGING),
            "calling_lock": _communication_lock(profile, CommunicationSchedule.Feature.CALLING),
            "incoming_call": incoming_call,
            "livekit_configured": _livekit_configured(),
            "call_allowance": _child_call_allowance(profile),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def message_thread(request, recipient_pk):
    profile = _profile(request)
    recipient = get_object_or_404(Profile, pk=recipient_pk)
    if recipient.pk == profile.pk:
        messages.error(request, "Choose another family member to send a message.")
        return redirect("messages_inbox")
    messaging_lock = _communication_lock(profile, CommunicationSchedule.Feature.MESSAGING)
    calling_lock = _communication_lock(profile, CommunicationSchedule.Feature.CALLING)
    profile.received_family_messages.filter(sender=recipient, read_at__isnull=True).update(read_at=timezone.now())
    if request.method == "POST":
        form = FamilyMessageForm(request.POST)
        if messaging_lock:
            messages.error(request, "Messaging is locked by your family schedule right now.")
        elif form.is_valid():
            message = form.save(commit=False)
            message.sender = profile
            message.recipient = recipient
            message.save()
            _notify(recipient, Notification.Kind.MESSAGE, f"Message from {profile.display_name}", message.body)
            return redirect("message_thread", recipient_pk=recipient.pk)
        else:
            messages.error(request, "Write a message before sending.")
    else:
        form = FamilyMessageForm()
    return render(
        request,
        "rewards/message_thread.html",
        {
            "profile": profile,
            "recipient": recipient,
            "thread_messages": FamilyMessage.objects.filter(_message_query(profile, recipient)).select_related("sender"),
            "message_form": form,
            "unread_message_count": _unread_message_count(profile),
            "messaging_lock": messaging_lock,
            "calling_lock": calling_lock,
            "incoming_call": None if calling_lock else _incoming_call(profile),
            "livekit_configured": _livekit_configured(),
            "call_allowance": _child_call_allowance(profile),
        },
    )


@login_required
@require_POST
def start_family_call(request, recipient_pk, call_type):
    caller = _profile(request)
    recipient = get_object_or_404(Profile, pk=recipient_pk)
    if recipient.pk == caller.pk or call_type not in FamilyCall.Type.values:
        messages.error(request, "Choose a valid family member and call type.")
        return redirect("messages_inbox")
    if not _livekit_configured():
        messages.error(request, "Video calling has not been configured by a parent yet.")
        return redirect("message_thread", recipient_pk=recipient.pk)
    for participant in (caller, recipient):
        if _communication_lock(participant, CommunicationSchedule.Feature.CALLING):
            messages.error(request, f"Calling is locked for {participant.display_name} by the family schedule right now.")
            return redirect("message_thread", recipient_pk=recipient.pk)
    _expire_ringing_calls()
    now = timezone.now()
    token_cost = 0
    call_number = None
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(child=caller) if caller.role == Profile.Role.CHILD else None
        existing = FamilyCall.objects.select_for_update().filter(
            Q(caller=caller, recipient=recipient) | Q(caller=recipient, recipient=caller),
            status__in=[FamilyCall.Status.RINGING, FamilyCall.Status.ACTIVE],
            created_at__gte=now - timedelta(minutes=30),
        ).first()
        if existing and existing.access_expires_at and existing.access_expires_at <= now:
            existing.status = FamilyCall.Status.ENDED
            existing.ended_at = now
            existing.save(update_fields=["status", "ended_at"])
            existing = None
        if existing:
            return redirect("call_room", pk=existing.pk)
        allowance_day = None
        if caller.role == Profile.Role.CHILD:
            allowance_day = timezone.localdate()
            prior_calls = FamilyCall.objects.filter(caller=caller, allowance_day=allowance_day).count()
            free_limit = max(settings.FREE_CHILD_CALLS_PER_DAY, 0)
            call_number = prior_calls + 1
            token_cost = 0 if prior_calls < free_limit else max(settings.CHILD_CALL_TOKEN_COST, 0)
            if token_cost and caller.grounded:
                messages.error(request, "Grounded Mode is active. Paid calls cannot use tokens right now.")
                return redirect("message_thread", recipient_pk=recipient.pk)
            if token_cost and wallet.tokens < token_cost:
                token_label = "token" if token_cost == 1 else "tokens"
                messages.error(request, f"You have used today's {free_limit} free calls and need {token_cost} {token_label} to start another call.")
                return redirect("message_thread", recipient_pk=recipient.pk)
            if token_cost:
                Wallet.objects.filter(pk=wallet.pk).update(tokens=F("tokens") - token_cost)
                description = f"Family call to {recipient.display_name}"
                entry = LedgerRequest.objects.create(
                    child=caller,
                    requested_by=caller,
                    kind=LedgerRequest.Kind.CALL,
                    description=description,
                    token_delta=-token_cost,
                    status=LedgerRequest.Status.APPROVED,
                    reviewed_at=now,
                )
                token_label = "token" if token_cost == 1 else "tokens"
                _notify(caller, Notification.Kind.CALL, "Call token used", f"{description}: -{token_cost} {token_label}.")
                _audit(caller, caller, "call_tokens_spent", description, ledger=entry)
        call = FamilyCall.objects.create(
            caller=caller,
            recipient=recipient,
            call_type=call_type,
            allowance_day=allowance_day,
            token_cost=token_cost,
        )
        label = call.get_call_type_display().lower()
        FamilyMessage.objects.create(sender=caller, recipient=recipient, body=f"Started a {label} call.")
        _notify(recipient, Notification.Kind.CALL, f"Incoming {label} call", f"{caller.display_name} is calling you.")
    if caller.role == Profile.Role.CHILD:
        if token_cost:
            token_label = "token" if token_cost == 1 else "tokens"
            messages.info(request, f"This call used {token_cost} {token_label}. Reconnect within {max(settings.CALL_RECONNECT_MINUTES, 1)} minutes without another charge.")
        else:
            messages.info(request, f"Free family call {call_number} of {max(settings.FREE_CHILD_CALLS_PER_DAY, 0)} today.")
    return redirect("call_room", pk=call.pk)


@login_required
@require_http_methods(["GET"])
def call_room(request, pk):
    profile = _profile(request)
    call = get_object_or_404(FamilyCall.objects.select_related("caller", "recipient"), pk=pk)
    if not call.includes(profile):
        return redirect("messages_inbox")
    contact = call.recipient if call.caller_id == profile.pk else call.caller
    call_lock = _communication_lock(profile, CommunicationSchedule.Feature.CALLING)
    if call_lock:
        messages.error(request, "Calls are locked by your family schedule right now.")
        return redirect("message_thread", recipient_pk=contact.pk)
    can_join = call.status == FamilyCall.Status.ACTIVE or (
        call.caller_id == profile.pk and call.status == FamilyCall.Status.RINGING
    )
    return render(
        request,
        "rewards/call_room.html",
        {
            "profile": profile,
            "call": call,
            "contact": contact,
            "can_join": can_join,
            "livekit_configured": _livekit_configured(),
        },
    )


@login_required
@require_POST
def accept_family_call(request, pk):
    profile = _profile(request)
    call = get_object_or_404(FamilyCall.objects.select_related("caller", "recipient"), pk=pk, recipient=profile)
    locked_participant, _ = _call_schedule_lock(call)
    if locked_participant:
        messages.error(request, f"Calls are locked for {locked_participant.display_name} by the family schedule right now.")
        return redirect("message_thread", recipient_pk=call.caller_id)
    if call.status == FamilyCall.Status.RINGING:
        call.status = FamilyCall.Status.ACTIVE
        call.answered_at = timezone.now()
        call.save(update_fields=["status", "answered_at"])
    return redirect("call_room", pk=call.pk)


@login_required
@require_POST
def decline_family_call(request, pk):
    profile = _profile(request)
    call = get_object_or_404(FamilyCall, pk=pk, recipient=profile)
    if call.status == FamilyCall.Status.RINGING:
        call.status = FamilyCall.Status.DECLINED
        call.ended_at = timezone.now()
        call.save(update_fields=["status", "ended_at"])
        FamilyMessage.objects.create(sender=profile, recipient=call.caller, body=f"Declined {call.get_call_type_display().lower()} call.")
    return redirect("message_thread", recipient_pk=call.caller_id)


@login_required
@require_POST
def end_family_call(request, pk):
    profile = _profile(request)
    call = get_object_or_404(FamilyCall, pk=pk)
    if not call.includes(profile):
        return redirect("messages_inbox")
    contact = call.recipient if call.caller_id == profile.pk else call.caller
    if call.status in [FamilyCall.Status.RINGING, FamilyCall.Status.ACTIVE]:
        call.status = FamilyCall.Status.ENDED
        call.ended_at = timezone.now()
        call.save(update_fields=["status", "ended_at"])
        FamilyMessage.objects.create(sender=profile, recipient=contact, body=f"Ended {call.get_call_type_display().lower()} call.")
    return redirect("message_thread", recipient_pk=contact.pk)


@login_required
@require_http_methods(["GET"])
def call_token(request, pk):
    profile = _profile(request)
    with transaction.atomic():
        call = get_object_or_404(FamilyCall.objects.select_for_update().select_related("caller", "recipient"), pk=pk)
        if not call.includes(profile):
            return JsonResponse({"error": "Not permitted."}, status=403)
        if not _livekit_configured():
            return JsonResponse({"error": "Calling is not configured."}, status=503)
        locked_participant, _ = _call_schedule_lock(call)
        if locked_participant:
            return JsonResponse({"error": "Calls are locked right now."}, status=403)
        may_join = call.status == FamilyCall.Status.ACTIVE or (
            call.caller_id == profile.pk and call.status == FamilyCall.Status.RINGING
        )
        if not may_join:
            return JsonResponse({"error": "This call is not available to join."}, status=403)
        if not call.access_expires_at:
            call.access_expires_at = timezone.now() + timedelta(minutes=max(settings.CALL_RECONNECT_MINUTES, 1))
            call.save(update_fields=["access_expires_at"])
        if call.access_expires_at <= timezone.now():
            return JsonResponse(
                {"error": f"The {max(settings.CALL_RECONNECT_MINUTES, 1)}-minute reconnect window has ended. Start a new call."},
                status=409,
            )
        try:
            token = _make_livekit_token(profile, call)
        except ValidationError as error:
            return JsonResponse({"error": error.message}, status=409)
    return JsonResponse({"wsUrl": settings.LIVEKIT_WS_URL, "token": token, "callType": call.call_type})


@login_required
@require_http_methods(["GET"])
def call_status(request, pk):
    profile = _profile(request)
    _expire_ringing_calls()
    call = get_object_or_404(FamilyCall.objects.select_related("caller", "recipient"), pk=pk)
    if not call.includes(profile):
        return JsonResponse({"error": "Not permitted."}, status=403)
    locked_participant, _ = _call_schedule_lock(call)
    if (
        locked_participant
        and call.status in [FamilyCall.Status.RINGING, FamilyCall.Status.ACTIVE]
    ):
        call.status = FamilyCall.Status.ENDED
        call.ended_at = timezone.now()
        call.save(update_fields=["status", "ended_at"])
        return JsonResponse({"status": call.status, "reason": "schedule"})
    return JsonResponse({"status": call.status})


@login_required
@require_http_methods(["GET"])
def incoming_call_status(request):
    profile = _profile(request)
    if _communication_lock(profile, CommunicationSchedule.Feature.CALLING):
        return JsonResponse({"call": None})
    call = _incoming_call(profile)
    if not call:
        return JsonResponse({"call": None})
    return JsonResponse(
        {
            "call": {
                "id": call.pk,
                "caller": call.caller.display_name,
                "type": call.get_call_type_display(),
                "url": f"/calls/{call.pk}/",
            }
        }
    )


@login_required
def child_section(request, section):
    if section not in CHILD_SECTIONS:
        return redirect("dashboard")
    ensure_today_chores()
    _expire_rules()
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if profile.grounded and section not in {"today", "chores"}:
        messages.info(request, "That area is available again when Grounded Mode is lifted.")
        return redirect("dashboard")
    context = _child_context(profile, FamilySettings.load(), include_welcome=False)
    context["active_section"] = section
    return render(request, "rewards/child_section.html", context)


@login_required
def wallet_page(request):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    context = {"profile": profile}
    context.update(_wallet_context(profile))
    return render(request, "rewards/wallet_page.html", context)


@login_required
def shopping_page(request):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    products = ShoppingProduct.objects.filter(active=True, in_stock=True)
    category = request.GET.get("category", "")
    search = request.GET.get("q", "").strip()
    if category in ShoppingProduct.Category.values:
        products = products.filter(category=category)
    if search:
        products = products.filter(Q(name__icontains=search) | Q(description__icontains=search))
    products = [product for product in products if product.available_to(profile)]
    cart_items = list(profile.shopping_cart_items.select_related("product"))
    context = {
        "profile": profile,
        "wallet": profile.wallet,
        "products": products,
        "categories": ShoppingProduct.Category.choices,
        "selected_category": category,
        "search": search,
        "cart_items": cart_items,
        "cart_total_cents": sum(item.subtotal_cents for item in cart_items),
        "orders": profile.shopping_orders.prefetch_related("items")[:12],
    }
    return render(request, "rewards/shopping_page.html", context)


@login_required
def discover_page(request):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if profile.grounded:
        messages.info(request, "Discover is locked while Grounded Mode is active.")
        return redirect("dashboard")
    schedule_lock = _discover_lock(profile)
    clips = [] if schedule_lock else list(_assigned_discover_clips(profile))
    source_playlists = [] if schedule_lock else list(_assigned_discover_playlists(profile))
    favorites = set(profile.video_favorites.filter(clip__in=clips).values_list("clip_id", flat=True))
    for clip in clips:
        clip.favorited = clip.pk in favorites
    return render(
        request,
        "rewards/discover_page.html",
        {
            "profile": profile,
            "clips": clips,
            "source_playlists": source_playlists,
            "discover_lock": schedule_lock,
            "youtube_embed_origin": quote(f"{request.scheme}://{request.get_host()}", safe=""),
        },
    )


@login_required
@require_http_methods(["GET"])
def discover_status(request):
    profile = _profile(request)
    if profile.role != Profile.Role.CHILD:
        return JsonResponse({"error": "Discover status is for child accounts only."}, status=403)
    schedule_lock = _discover_lock(profile)
    if profile.grounded:
        return JsonResponse({"locked": True, "reason": "grounded"})
    if schedule_lock:
        return JsonResponse({"locked": True, "reason": "schedule"})
    return JsonResponse({"locked": False})


@login_required
@require_POST
def discover_favorite(request, pk):
    profile = _profile(request)
    if profile.role != Profile.Role.CHILD or profile.grounded or _discover_lock(profile):
        return JsonResponse({"error": "Discover is not available right now."}, status=403)
    clip = get_object_or_404(_assigned_discover_clips(profile), pk=pk)
    favorite, created = VideoFavorite.objects.get_or_create(child=profile, clip=clip)
    if not created:
        favorite.delete()
    payload = {"favorited": created}
    if request.headers.get("Accept") == "application/json":
        return JsonResponse(payload)
    return redirect("discover_page")


@login_required
@require_POST
def discover_watch(request, pk):
    profile = _profile(request)
    if profile.role != Profile.Role.CHILD or profile.grounded or _discover_lock(profile):
        return JsonResponse({"error": "Discover is not available right now."}, status=403)
    clip = get_object_or_404(_assigned_discover_clips(profile), pk=pk)
    with transaction.atomic():
        event, created = VideoWatchEvent.objects.select_for_update().get_or_create(child=profile, clip=clip)
        if not created:
            event.view_count = F("view_count") + 1
            event.save(update_fields=["view_count", "last_watched_at"])
            event.refresh_from_db(fields=["view_count"])
    return JsonResponse({"views": event.view_count})


@login_required
@require_http_methods(["GET"])
def shopping_product_photo(request, pk):
    _profile(request)
    product = get_object_or_404(ShoppingProduct, pk=pk)
    return _shopping_photo_fallback(product.category)


@login_required
@require_http_methods(["GET"])
def shopping_order_item_photo(request, pk):
    profile = _profile(request)
    item = get_object_or_404(ShoppingOrderItem.objects.select_related("order__child", "product"), pk=pk)
    can_fulfill = profile.is_guardian or (
        profile.role == Profile.Role.VIEWER and profile.user.username.lower() == "mom"
    )
    if item.order.child_id != profile.pk and not can_fulfill:
        raise Http404
    category = item.product.category if item.product else "gift"
    return _shopping_photo_fallback(category)


@login_required
@require_POST
def shopping_cart_add(request, pk):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    product = get_object_or_404(ShoppingProduct, pk=pk)
    if not product.available_to(profile):
        messages.error(request, "That product is not currently available to request.")
        return redirect("shopping_page")
    item, created = ShoppingCartItem.objects.get_or_create(child=profile, product=product)
    if not created:
        if item.quantity >= 10:
            messages.info(request, "Your cart can hold up to 10 of one item.")
            return redirect("shopping_page")
        item.quantity += 1
        item.save(update_fields=["quantity"])
    messages.success(request, f"{product.name} added to your cart.")
    return redirect("shopping_page")


@login_required
@require_POST
def shopping_cart_update(request, pk):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    item = get_object_or_404(ShoppingCartItem.objects.select_related("product"), pk=pk, child=profile)
    action = request.POST.get("action")
    if action == "remove" or (action == "decrease" and item.quantity == 1):
        item.delete()
        messages.info(request, "Removed from your cart.")
    elif action == "decrease":
        item.quantity -= 1
        item.save(update_fields=["quantity"])
    elif action == "increase" and item.product.available_to(profile) and item.quantity < 10:
        item.quantity += 1
        item.save(update_fields=["quantity"])
    return redirect("shopping_page")


@login_required
@require_POST
def shopping_checkout(request):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    with transaction.atomic():
        cart_items = list(
            ShoppingCartItem.objects.select_for_update()
            .filter(child=profile)
            .select_related("product")
        )
        if not cart_items:
            messages.error(request, "Add something to your cart before sending an order.")
            return redirect("shopping_page")
        if any(not item.product.available_to(profile) for item in cart_items):
            messages.error(request, "An item in your cart is no longer available. Please review your cart.")
            return redirect("shopping_page")
        total = sum(item.subtotal_cents for item in cart_items)
        wallet = Wallet.objects.select_for_update().get(child=profile)
        sources = _cash_sources(wallet, total)
        if sources is None:
            messages.error(request, "Your Cash App balance is not enough for this cart.")
            return redirect("shopping_page")
        wallet_cash, legacy_cash = sources
        Wallet.objects.filter(pk=wallet.pk).update(
            cash_cents=F("cash_cents") - wallet_cash,
            spending_cents=F("spending_cents") - legacy_cash,
        )
        ledger = LedgerRequest.objects.create(
            child=profile,
            requested_by=profile,
            kind=LedgerRequest.Kind.SHOPPING,
            description=f"Shopping order reserved: ${total / 100:.2f}",
            cash_delta_cents=-wallet_cash,
            spending_delta_cents=-legacy_cash,
        )
        order = ShoppingOrder.objects.create(
            child=profile,
            reservation_ledger=ledger,
            quoted_total_cents=total,
            held_cash_cents=wallet_cash,
            held_spending_cents=legacy_cash,
        )
        ShoppingOrderItem.objects.bulk_create(
            [
                ShoppingOrderItem(
                    order=order,
                    product=item.product,
                    product_name=item.product.name,
                    retailer=item.product.retailer,
                    retailer_url=item.product.retailer_url,
                    unit_price_cents=item.product.retail_price_cents,
                    quantity=item.quantity,
                )
                for item in cart_items
            ]
        )
        ShoppingCartItem.objects.filter(child=profile).delete()
        _notify(profile, Notification.Kind.SHOPPING, "Order sent to your parents", f"${total / 100:.2f} is reserved while they purchase your cart.")
        _audit(profile, profile, "shopping_order_submitted", f"Shopping order #{order.pk}: ${total / 100:.2f} reserved.", ledger=ledger)
    messages.success(request, "Your cart was sent to your parents. The money is safely reserved until they complete or cancel it.")
    return redirect("shopping_page")


@login_required
@require_POST
def start_chore(request, pk):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    chore = get_object_or_404(Chore, pk=pk, child=profile, status=Chore.Status.OPEN)
    chore.status = Chore.Status.IN_PROGRESS
    chore.save(update_fields=["status"])
    cutoff = "10 AM" if chore.optional else "7 PM"
    if profile.grounded:
        messages.info(request, "You started it. Tap finished before the deadline so a guardian can verify your work.")
    else:
        messages.info(request, f"You started it. Tap finished before {cutoff} to earn your tokens!")
    return _child_destination(request)


@login_required
@require_POST
def submit_chore(request, pk):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    chore = get_object_or_404(Chore, pk=pk, child=profile, status__in=[Chore.Status.OPEN, Chore.Status.IN_PROGRESS])
    now = timezone.localtime()
    late = (chore.due_date and chore.due_date < now.date()) or (
        (not chore.due_date or chore.due_date == now.date()) and now.time() > chore.credit_deadline
    )
    if late:
        chore.status = Chore.Status.LATE
        chore.save(update_fields=["status"])
        cutoff = "10 AM" if chore.optional else "7 PM"
        messages.info(request, f"Marked finished. It was after {cutoff}, so this chore does not earn tokens today.")
        return _child_destination(request)
    earns_rewards = not profile.grounded
    LedgerRequest.objects.create(
        child=profile,
        requested_by=profile,
        kind=LedgerRequest.Kind.CHORE,
        description=f"{'Completed chore' if earns_rewards else 'Grounded chore check'}: {chore.title}",
        token_delta=chore.token_reward if earns_rewards else 0,
        cash_delta_cents=0,
        chore=chore,
    )
    chore.status = Chore.Status.SUBMITTED
    chore.save(update_fields=["status"])
    if earns_rewards:
        messages.success(request, "Nice work. A guardian can now approve your chore reward.")
    else:
        messages.success(request, "Nice work. A guardian can verify your chore, but Grounded Mode adds no tokens.")
    return _child_destination(request)


@login_required
@require_POST
def submit_goal(request, pk):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return _child_destination(request)
    goal = get_object_or_404(GrowthGoal, pk=pk, child=profile, status=GrowthGoal.Status.ACTIVE)
    LedgerRequest.objects.create(
        child=profile,
        requested_by=profile,
        kind=LedgerRequest.Kind.GOAL,
        description=f"Reached goal: {goal.title}",
        token_delta=goal.token_reward,
        goal=goal,
    )
    goal.status = GrowthGoal.Status.SUBMITTED
    goal.save(update_fields=["status"])
    messages.success(request, "Goal submitted for celebration and approval.")
    return _child_destination(request)


@login_required
@require_POST
def buy_item(request, pk):
    profile = _profile(request)
    item = get_object_or_404(StoreItem, pk=pk)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return _child_destination(request)
    if not item.available_to(profile):
        messages.error(request, "This store item is not currently available for your account.")
        return _child_destination(request)
    if profile.wallet.tokens < item.token_cost or profile.wallet.cash_cents < item.cash_cost_cents:
        messages.error(request, "You do not have enough tokens or wallet cash for that reward.")
        return _child_destination(request)
    with transaction.atomic():
        entry = LedgerRequest.objects.create(
            child=profile,
            requested_by=profile,
            kind=LedgerRequest.Kind.STORE,
            description=f"Store redemption: {item.name}",
            token_delta=-item.token_cost,
            cash_delta_cents=-item.cash_cost_cents,
            store_item=item,
        )
        Purchase.objects.create(
            child=profile,
            item=item,
            ledger=entry,
            token_cost=item.token_cost,
            cash_cost_cents=item.cash_cost_cents,
        )
        if not item.requires_approval:
            entry.approve()
    if item.requires_approval:
        messages.success(request, "Store request sent to your parents for approval.")
    else:
        messages.success(request, "Reward unlocked! Your purchase is recorded in your wallet.")
    return _child_destination(request)


@login_required
@require_POST
def request_conversion(request):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    messages.info(request, "Wallet cash cannot be converted into tokens. Complete chores to earn tokens.")
    return redirect("wallet_page")


@login_required
@require_POST
def request_token_cashout(request):
    profile = _profile(request)
    form = TokenCashoutForm(request.POST)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    if not form.is_valid():
        messages.error(request, "Enter the number of tokens you want to cash out.")
        return redirect("wallet_page")
    tokens = form.cleaned_data["tokens"]
    if tokens > profile.wallet.tokens:
        messages.error(request, "You do not have enough tokens for that cash-out request.")
        return redirect("wallet_page")
    family_settings = FamilySettings.load()
    cents = _cash_for_tokens(tokens, family_settings)
    note = form.cleaned_data.get("note", "")
    description = f"Cash out {tokens} tokens to ${cents / 100:.2f} wallet cash"
    if note:
        description = f"{description}: {note}"
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(child=profile)
        if tokens > wallet.tokens:
            messages.error(request, "You do not have enough tokens for that cash-out request.")
            return redirect("wallet_page")
        Wallet.objects.filter(pk=wallet.pk).update(tokens=F("tokens") - tokens, cash_cents=F("cash_cents") + cents)
        entry = LedgerRequest.objects.create(
            child=profile,
            requested_by=profile,
            kind=LedgerRequest.Kind.CASH_OUT,
            description=description,
            token_delta=-tokens,
            cash_delta_cents=cents,
            status=LedgerRequest.Status.APPROVED,
            reviewed_at=timezone.now(),
        )
        _notify(profile, Notification.Kind.WALLET, "Tokens converted to wallet cash", description)
        _audit(profile, profile, "token_cashout_completed", description, ledger=entry)
    messages.success(request, f"Converted {tokens} tokens into ${cents / 100:.2f} wallet cash.")
    return redirect("wallet_page")


@login_required
@require_POST
def request_tokens_to_savings(request):
    return request_token_cashout(request)


@login_required
@require_POST
def request_cashout(request):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    messages.info(request, "Your wallet cash is real-world spending money. A parent marks it spent after you use it.")
    return redirect("wallet_page")


@login_required
@require_POST
def request_spending_transfer(request):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    messages.info(request, "Your Cash App balance is already available to send or spend. No transfer is needed.")
    return redirect("wallet_page")


@login_required
@require_POST
def send_token_gift(request):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    form = TokenGiftForm(request.POST, sender=profile)
    if not form.is_valid():
        messages.error(request, "Choose a sibling and a valid number of tokens to send.")
        return redirect("wallet_page")
    recipient = form.cleaned_data["recipient_id"]
    tokens = form.cleaned_data["tokens"]
    recipient.refresh_grounding()
    if recipient.grounded:
        messages.error(request, "That sibling is in Grounded Mode and cannot receive tokens right now.")
        return redirect("wallet_page")
    with transaction.atomic():
        wallets = {
            wallet.child_id: wallet
            for wallet in Wallet.objects.select_for_update().filter(child_id__in=[profile.pk, recipient.pk]).order_by("pk")
        }
        if tokens > wallets[profile.pk].tokens:
            messages.error(request, "You do not have enough tokens to send that gift.")
            return redirect("wallet_page")
        Wallet.objects.filter(pk=wallets[profile.pk].pk).update(tokens=F("tokens") - tokens)
        Wallet.objects.filter(pk=wallets[recipient.pk].pk).update(tokens=F("tokens") + tokens)
        timestamp = timezone.now()
        sent = LedgerRequest.objects.create(
            child=profile,
            requested_by=profile,
            counterparty=recipient,
            kind=LedgerRequest.Kind.GIFT,
            description=f"Sent {tokens} tokens to {recipient.display_name}",
            token_delta=-tokens,
            status=LedgerRequest.Status.APPROVED,
            reviewed_at=timestamp,
        )
        received = LedgerRequest.objects.create(
            child=recipient,
            requested_by=profile,
            counterparty=profile,
            kind=LedgerRequest.Kind.GIFT,
            description=f"Received {tokens} tokens from {profile.display_name}",
            token_delta=tokens,
            status=LedgerRequest.Status.APPROVED,
            reviewed_at=timestamp,
        )
        _notify(recipient, Notification.Kind.REWARD, "Token gift received", received.description)
        _audit(profile, profile, "token_gift_sent", sent.description, ledger=sent)
    messages.success(request, f"{tokens} token{'s' if tokens != 1 else ''} sent to {recipient.display_name}.")
    return redirect("wallet_page")


@login_required
@require_POST
def send_family_transfer(request):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    form = FamilyTransferForm(request.POST, sender=profile)
    if not form.is_valid():
        messages.error(request, "Choose a sibling and enter a cash amount to send.")
        return redirect("wallet_page")
    recipient = form.cleaned_data["recipient_id"]
    cents = _cents(form.cleaned_data["cash_amount"])
    recipient.refresh_grounding()
    if recipient.grounded:
        messages.error(request, "That sibling is in Grounded Mode and cannot receive money right now.")
        return redirect("wallet_page")
    with transaction.atomic():
        wallets = {
            wallet.child_id: wallet
            for wallet in Wallet.objects.select_for_update().filter(child_id__in=[profile.pk, recipient.pk]).order_by("pk")
        }
        sources = _cash_sources(wallets[profile.pk], cents)
        if sources is None:
            messages.error(request, "You do not have enough cash to send that amount.")
            return redirect("wallet_page")
        wallet_cash, legacy_cash = sources
        Wallet.objects.filter(pk=wallets[profile.pk].pk).update(
            cash_cents=F("cash_cents") - wallet_cash,
            spending_cents=F("spending_cents") - legacy_cash,
        )
        Wallet.objects.filter(pk=wallets[recipient.pk].pk).update(cash_cents=F("cash_cents") + cents)
        timestamp = timezone.now()
        sent = LedgerRequest.objects.create(
            child=profile,
            requested_by=profile,
            counterparty=recipient,
            kind=LedgerRequest.Kind.GIFT,
            description=f"Sent ${cents / 100:.2f} to {recipient.display_name}",
            cash_delta_cents=-wallet_cash,
            spending_delta_cents=-legacy_cash,
            status=LedgerRequest.Status.APPROVED,
            reviewed_at=timestamp,
        )
        received = LedgerRequest.objects.create(
            child=recipient,
            requested_by=profile,
            counterparty=profile,
            kind=LedgerRequest.Kind.GIFT,
            description=f"Received ${cents / 100:.2f} from {profile.display_name}",
            cash_delta_cents=cents,
            status=LedgerRequest.Status.APPROVED,
            reviewed_at=timestamp,
        )
        _notify(recipient, Notification.Kind.WALLET, "Sibling payment received", received.description)
        _audit(profile, profile, "wallet_transfer_sent", sent.description, ledger=sent)
    messages.success(request, f"${cents / 100:.2f} sent to {recipient.display_name}.", extra_tags="payment-success sent")
    return redirect("wallet_page")


@login_required
@require_POST
def request_store_spend(request):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    form = SpendingTransferForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a valid amount for your in-person purchase.")
        return redirect("wallet_page")
    cents = _cents(form.cleaned_data["cash_amount"])
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(child=profile)
        sources = _cash_sources(wallet, cents)
        if sources is None:
            messages.error(request, "You do not have enough cash for that purchase.")
            return redirect("wallet_page")
        wallet_cash, legacy_cash = sources
        Wallet.objects.filter(pk=wallet.pk).update(
            cash_cents=F("cash_cents") - wallet_cash,
            spending_cents=F("spending_cents") - legacy_cash,
        )
        LedgerRequest.objects.create(
            child=profile,
            requested_by=profile,
            kind=LedgerRequest.Kind.SPEND,
            description=f"In-person spending pending: ${cents / 100:.2f}",
            cash_delta_cents=-wallet_cash,
            spending_delta_cents=-legacy_cash,
        )
    messages.success(request, f"${cents / 100:.2f} reserved for spending. Dad will verify it.", extra_tags="payment-success spent")
    return redirect("wallet_page")


@login_required
@require_POST
def save_savings_goal(request):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return _child_destination(request)
    goal = SavingsGoal.objects.filter(child=profile).first()
    form = SavingsGoalForm(request.POST, instance=goal)
    if not form.is_valid():
        messages.error(request, "Please choose a goal name and a savings amount.")
        return _child_destination(request)
    goal = form.save(commit=False)
    goal.child = profile
    goal.target_cents = _cents(form.cleaned_data["target_amount"])
    goal.save()
    messages.success(request, f"Your savings goal is set: {goal.name}!")
    return _child_destination(request)


@login_required
@require_POST
def dismiss_recap(request):
    profile = _profile(request)
    if profile.role == Profile.Role.CHILD:
        profile.last_recap_at = timezone.now()
        profile.last_recap_day = timezone.localdate()
        profile.save(update_fields=["last_recap_at", "last_recap_day"])
        visible_notice_ids = list(
            profile.notifications.filter(read_at__isnull=True).values_list("pk", flat=True)[:10]
        )
        profile.notifications.filter(pk__in=visible_notice_ids).update(read_at=timezone.now())
    return redirect("dashboard")


@login_required
@require_POST
def guardian_create(request, model):
    guardian = _guardian(request)
    if guardian is None:
        return redirect("dashboard")
    if model == "house_rule":
        form = HouseRuleForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please check the house rule and try again.")
            return redirect(f"/?child={request.POST.get('child_id', '')}")
        record = form.save(commit=False)
        record.created_by = guardian
        record.save()
        for child in Profile.objects.filter(role=Profile.Role.CHILD):
            _notify(child, Notification.Kind.RULE, "New house rule", record.title)
        _audit(guardian, None, "house_rule_created", record.title, house_rule=record)
        messages.success(request, "House rule added for everyone.")
        return redirect(f"/?child={request.POST.get('child_id', '')}")
    child = get_object_or_404(Profile, pk=request.POST.get("child_id"), role=Profile.Role.CHILD)
    if model == "schedule" and guardian.user.username.lower() != "dad":
        messages.error(request, "Only Dad can create or publish family schedule events.")
        return redirect(f"/?child={child.pk}")
    forms = {
        "grade": GradeForm,
        "chore": ChoreForm,
        "goal": GoalForm,
        "item": StoreItemForm,
        "schedule": DailyScheduleEventForm,
        "child_rule": ChildRuleForm,
    }
    form_class = forms.get(model)
    if not form_class:
        return redirect("dashboard")
    form = form_class(request.POST)
    if not form.is_valid():
        messages.error(request, "Please check the form and try again.")
        return redirect(f"/?child={child.pk}")
    record = form.save(commit=False)
    if model == "item":
        record.save()
    else:
        record.child = child
        if model == "grade":
            record.recorded_by = guardian
        if model == "chore":
            record.cash_reward_cents = 0
            record.due_date = timezone.localdate()
            record.assigned_by = guardian
        if model in ["schedule", "child_rule"]:
            record.created_by = guardian
        record.save()
    if model == "chore":
        _notify(child, Notification.Kind.CHORE, "New chore assigned", f"{record.title} earns {record.token_reward} tokens after approval.")
    if model == "child_rule":
        _notify(child, Notification.Kind.RULE, "Individual rule updated", record.title)
        _audit(guardian, child, "child_rule_created", record.title, child_rule=record)
    if model == "item":
        _audit(guardian, None, "store_item_created", record.name)
    labels = {"schedule": "Schedule event", "child_rule": "Personal rule"}
    if model == "schedule":
        messages.success(request, f"Event queued for {child.display_name}. Dad must approve that date before it appears for the child.")
    else:
        messages.success(request, f"{labels.get(model, model.title())} added for {child.display_name}.")
    return redirect(f"/?child={child.pk}")


@login_required
@require_POST
def guardian_child_profile(request):
    guardian = _guardian(request)
    child = get_object_or_404(Profile, pk=request.POST.get("child_id"), role=Profile.Role.CHILD)
    if guardian is None:
        return redirect("dashboard")
    form = ChildProfileForm(request.POST, instance=child)
    if not form.is_valid():
        messages.error(request, "Please enter a valid birth date.")
        return redirect(f"/?child={child.pk}")
    form.save()
    _audit(guardian, child, "child_profile_updated", "Store eligibility profile updated.")
    messages.success(request, f"{child.display_name}'s store eligibility profile was updated.")
    return redirect(f"/?child={child.pk}")


@login_required
@require_POST
def guardian_edit(request, model, pk):
    guardian = _guardian(request)
    if guardian is None:
        return redirect("dashboard")
    models = {"child_rule": (ChildRule, ChildRuleForm), "house_rule": (HouseRule, HouseRuleForm), "item": (StoreItem, StoreItemForm)}
    entry = models.get(model)
    if entry is None:
        return redirect("dashboard")
    record_model, form_class = entry
    record = get_object_or_404(record_model, pk=pk)
    form = form_class(request.POST, instance=record)
    selected_id = getattr(record, "child_id", None) or request.POST.get("child_id", "")
    if not form.is_valid():
        messages.error(request, "Please check the changes and try again.")
        return redirect(f"/?child={selected_id}")
    form.save()
    if model == "house_rule":
        record.acknowledgements.all().delete()
        for child in Profile.objects.filter(role=Profile.Role.CHILD):
            _notify(child, Notification.Kind.RULE, "House rule updated", record.title)
        _audit(guardian, None, "house_rule_updated", record.title, house_rule=record)
    elif model == "child_rule":
        record.acknowledgements.all().delete()
        _notify(record.child, Notification.Kind.RULE, "Individual rule updated", record.title)
        _audit(guardian, record.child, "child_rule_updated", record.title, child_rule=record)
    else:
        _audit(guardian, None, "store_item_updated", record.name)
    messages.success(request, "Changes saved.")
    return redirect(f"/?child={selected_id}")


@login_required
@require_POST
def guardian_toggle(request, model, pk):
    guardian = _guardian(request)
    if guardian is None:
        return redirect("dashboard")
    record_model = {"child_rule": ChildRule, "house_rule": HouseRule, "item": StoreItem}.get(model)
    if record_model is None:
        return redirect("dashboard")
    record = get_object_or_404(record_model, pk=pk)
    record.active = not record.active
    record.save(update_fields=["active"])
    selected_id = getattr(record, "child_id", None) or request.POST.get("child_id", "")
    label = "enabled" if record.active else "paused"
    if model == "house_rule":
        for child in Profile.objects.filter(role=Profile.Role.CHILD):
            _notify(child, Notification.Kind.RULE, "House rules changed", f"{record.title} is now {label}.")
        _audit(guardian, None, f"house_rule_{label}", record.title, house_rule=record)
    elif model == "child_rule":
        _notify(record.child, Notification.Kind.RULE, "Individual rules changed", f"{record.title} is now {label}.")
        _audit(guardian, record.child, f"child_rule_{label}", record.title, child_rule=record)
    else:
        _audit(guardian, None, f"store_item_{label}", record.name)
    messages.info(request, f"{getattr(record, 'title', getattr(record, 'name', 'Item'))} {label}.")
    return redirect(f"/?child={selected_id}")


@login_required
@require_POST
def guardian_remove(request, model, pk):
    guardian = _guardian(request)
    if guardian is None:
        return redirect("dashboard")
    models = {"schedule": DailyScheduleEvent, "child_rule": ChildRule, "house_rule": HouseRule}
    record_model = models.get(model)
    if record_model is None:
        return redirect("dashboard")
    record = get_object_or_404(record_model, pk=pk)
    selected_id = getattr(record, "child_id", None) or request.POST.get("child_id", "")
    if model == "schedule":
        if guardian.user.username.lower() != "dad":
            messages.error(request, "Only Dad can change the published family schedule.")
            return redirect(f"/?child={selected_id}")
        record.delete()
    elif model == "house_rule":
        for child in Profile.objects.filter(role=Profile.Role.CHILD):
            _notify(child, Notification.Kind.RULE, "House rule removed", record.title)
        _audit(guardian, None, "house_rule_deleted", record.title, house_rule=record)
        record.delete()
    else:
        child = record.child
        _notify(child, Notification.Kind.RULE, "Individual rule removed", record.title)
        _audit(guardian, child, "child_rule_deleted", record.title, child_rule=record)
        record.delete()
    messages.info(request, "Item deleted.")
    return redirect(f"/?child={selected_id}")


@login_required
@require_POST
def dad_shopping_product_create(request):
    dad = _dad(request)
    selected_id = request.POST.get("child_id", "")
    if dad is None:
        return redirect("dashboard")
    form = ShoppingProductForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please check the shopping product information and try again.")
        return redirect(f"/?child={selected_id}")
    product = form.save(commit=False)
    product.added_by = dad
    product.save()
    _audit(dad, None, "shopping_product_created", product.name)
    messages.success(request, f"{product.name} added to Shopping.")
    return redirect(f"/?child={selected_id}")


@login_required
@require_POST
def dad_shopping_product_edit(request, pk):
    dad = _dad(request)
    selected_id = request.POST.get("child_id", "")
    if dad is None:
        return redirect("dashboard")
    product = get_object_or_404(ShoppingProduct, pk=pk)
    form = ShoppingProductForm(request.POST, instance=product)
    if not form.is_valid():
        messages.error(request, "Please check the shopping product changes and try again.")
        return redirect(f"/?child={selected_id}")
    form.save()
    _audit(dad, None, "shopping_product_updated", product.name)
    messages.success(request, "Shopping product updated.")
    return redirect(f"/?child={selected_id}")


@login_required
@require_POST
def dad_shopping_product_stock(request, pk):
    dad = _dad(request)
    selected_id = request.POST.get("child_id", "")
    if dad is None:
        return redirect("dashboard")
    product = get_object_or_404(ShoppingProduct, pk=pk)
    product.in_stock = not product.in_stock
    product.save(update_fields=["in_stock", "updated_at"])
    status = "back in stock" if product.in_stock else "out of stock"
    _audit(dad, None, "shopping_product_stock_changed", f"{product.name}: {status}")
    messages.info(request, f"{product.name} is {status}.")
    return redirect(f"/?child={selected_id}")


@login_required
@require_POST
def dad_shopping_product_toggle(request, pk):
    dad = _dad(request)
    selected_id = request.POST.get("child_id", "")
    if dad is None:
        return redirect("dashboard")
    product = get_object_or_404(ShoppingProduct, pk=pk)
    product.active = not product.active
    product.save(update_fields=["active", "updated_at"])
    status = "visible" if product.active else "hidden"
    _audit(dad, None, "shopping_product_visibility_changed", f"{product.name}: {status}")
    messages.info(request, f"{product.name} is now {status} in Shopping.")
    return redirect(f"/?child={selected_id}")


@login_required
@require_POST
def dad_shopping_product_delete(request, pk):
    dad = _dad(request)
    selected_id = request.POST.get("child_id", "")
    if dad is None:
        return redirect("dashboard")
    product = get_object_or_404(ShoppingProduct, pk=pk)
    name = product.name
    _audit(dad, None, "shopping_product_deleted", name)
    product.delete()
    messages.info(request, f"{name} removed from Shopping.")
    return redirect(f"/?child={selected_id}")


@login_required
@require_POST
def guardian_video_playlist_create(request):
    manager = _video_manager(request)
    selected_id = request.POST.get("child_id", "")
    if manager is None:
        return redirect("dashboard")
    form = VideoPlaylistForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please check the playlist information and try again.")
        return redirect(f"/?child={selected_id}#parent-video-library")
    playlist = form.save(commit=False)
    playlist.created_by = manager
    playlist.save()
    _audit(manager, None, "video_playlist_created", playlist.title)
    messages.success(request, f"{playlist.title} created in Video Library.")
    return redirect(f"/?child={selected_id}#parent-video-library")


@login_required
@require_POST
def guardian_video_playlist_edit(request, pk):
    manager = _video_manager(request)
    selected_id = request.POST.get("child_id", "")
    if manager is None:
        return redirect("dashboard")
    playlist = get_object_or_404(VideoPlaylist, pk=pk)
    form = VideoPlaylistForm(request.POST, instance=playlist)
    if not form.is_valid():
        messages.error(request, "Please check the playlist changes and try again.")
        return redirect(f"/?child={selected_id}#parent-video-library")
    form.save()
    _audit(manager, None, "video_playlist_updated", playlist.title)
    messages.success(request, "Discover playlist updated.")
    return redirect(f"/?child={selected_id}#parent-video-library")


@login_required
@require_POST
def guardian_video_playlist_toggle(request, pk):
    manager = _video_manager(request)
    selected_id = request.POST.get("child_id", "")
    if manager is None:
        return redirect("dashboard")
    playlist = get_object_or_404(VideoPlaylist, pk=pk)
    playlist.active = not playlist.active
    playlist.save(update_fields=["active", "updated_at"])
    status = "available" if playlist.active else "paused"
    _audit(manager, None, "video_playlist_visibility_changed", f"{playlist.title}: {status}")
    messages.info(request, f"{playlist.title} is now {status} in Discover.")
    return redirect(f"/?child={selected_id}#parent-video-library")


@login_required
@require_POST
def guardian_video_playlist_delete(request, pk):
    manager = _video_manager(request)
    selected_id = request.POST.get("child_id", "")
    if manager is None:
        return redirect("dashboard")
    playlist = get_object_or_404(VideoPlaylist, pk=pk)
    title = playlist.title
    _audit(manager, None, "video_playlist_deleted", title)
    playlist.delete()
    messages.info(request, f"{title} removed from Video Library.")
    return redirect(f"/?child={selected_id}#parent-video-library")


@login_required
@require_POST
def guardian_video_clip_add(request, playlist_pk):
    manager = _video_manager(request)
    selected_id = request.POST.get("child_id", "")
    if manager is None:
        return redirect("dashboard")
    playlist = get_object_or_404(VideoPlaylist, pk=playlist_pk)
    form = VideoClipForm(request.POST)
    video_id = _youtube_id(request.POST.get("youtube_url", ""))
    if not form.is_valid() or not video_id:
        messages.error(request, "Add a valid YouTube video or Shorts link and a title.")
        return redirect(f"/?child={selected_id}#parent-video-library")
    if playlist.clips.filter(youtube_id=video_id).exists():
        messages.info(request, "That video is already in this playlist.")
        return redirect(f"/?child={selected_id}#parent-video-library")
    position = (playlist.clips.aggregate(last=Max("position"))["last"] or 0) + 1
    VideoClip.objects.create(
        playlist=playlist,
        youtube_id=video_id,
        title=form.cleaned_data["title"].strip(),
        subject_tag=form.cleaned_data["subject_tag"].strip(),
        position=position,
        added_by=manager,
    )
    _audit(manager, None, "video_clip_added", f"{form.cleaned_data['title']} added to {playlist.title}.")
    messages.success(request, f"Video added to {playlist.title}.")
    return redirect(f"/?child={selected_id}#parent-video-library")


@login_required
@require_POST
def guardian_video_clip_toggle(request, pk):
    manager = _video_manager(request)
    selected_id = request.POST.get("child_id", "")
    if manager is None:
        return redirect("dashboard")
    clip = get_object_or_404(VideoClip.objects.select_related("playlist"), pk=pk)
    clip.active = not clip.active
    clip.save(update_fields=["active"])
    status = "shown" if clip.active else "hidden"
    _audit(manager, None, "video_clip_visibility_changed", f"{clip.title}: {status}")
    messages.info(request, f"{clip.title} is now {status} in Discover.")
    return redirect(f"/?child={selected_id}#parent-video-library")


@login_required
@require_POST
def guardian_video_clip_move(request, pk, direction):
    manager = _video_manager(request)
    selected_id = request.POST.get("child_id", "")
    if manager is None:
        return redirect("dashboard")
    clip = get_object_or_404(VideoClip.objects.select_related("playlist"), pk=pk)
    if direction == "up":
        neighbor = clip.playlist.clips.filter(position__lt=clip.position).order_by("-position").first()
    elif direction == "down":
        neighbor = clip.playlist.clips.filter(position__gt=clip.position).order_by("position").first()
    else:
        return redirect(f"/?child={selected_id}#parent-video-library")
    if neighbor:
        clip.position, neighbor.position = neighbor.position, clip.position
        clip.save(update_fields=["position"])
        neighbor.save(update_fields=["position"])
        _audit(manager, None, "video_clip_reordered", f"{clip.title} moved {direction} in {clip.playlist.title}.")
    return redirect(f"/?child={selected_id}#parent-video-library")


@login_required
@require_POST
def guardian_video_clip_delete(request, pk):
    manager = _video_manager(request)
    selected_id = request.POST.get("child_id", "")
    if manager is None:
        return redirect("dashboard")
    clip = get_object_or_404(VideoClip.objects.select_related("playlist"), pk=pk)
    description = f"{clip.title} removed from {clip.playlist.title}."
    clip.delete()
    _audit(manager, None, "video_clip_deleted", description)
    messages.info(request, description)
    return redirect(f"/?child={selected_id}#parent-video-library")


@login_required
@require_POST
def guardian_video_assignment_toggle(request, playlist_pk):
    manager = _video_manager(request)
    if manager is None:
        return redirect("dashboard")
    child = get_object_or_404(Profile, pk=request.POST.get("child_id"), role=Profile.Role.CHILD)
    playlist = get_object_or_404(VideoPlaylist, pk=playlist_pk)
    assignment, created = VideoPlaylistAssignment.objects.get_or_create(
        playlist=playlist,
        child=child,
        defaults={"assigned_by": manager},
    )
    if created:
        enabled = True
    else:
        assignment.enabled = not assignment.enabled
        assignment.assigned_by = manager
        assignment.save(update_fields=["enabled", "assigned_by"])
        enabled = assignment.enabled
    status = "assigned" if enabled else "removed"
    if enabled:
        _notify(child, Notification.Kind.DISCOVER, "Discover playlist assigned", f"{playlist.title} has been added to your Discover library.")
    _audit(manager, child, f"video_playlist_{status}", playlist.title)
    messages.info(request, f"{playlist.title} {status} for {child.display_name}.")
    return redirect(f"/?child={child.pk}#parent-video-library")


@login_required
@require_POST
def fulfillment_claim(request, pk):
    fulfiller = _fulfiller(request)
    if fulfiller is None:
        return redirect("dashboard")
    with transaction.atomic():
        order = get_object_or_404(ShoppingOrder.objects.select_for_update().select_related("child"), pk=pk)
        if order.status not in [ShoppingOrder.Status.SUBMITTED, ShoppingOrder.Status.CLAIMED]:
            messages.error(request, "That order is no longer waiting for fulfillment.")
            return redirect(f"/?child={order.child.pk}")
        order.status = ShoppingOrder.Status.CLAIMED
        order.assigned_to = fulfiller
        order.claimed_at = timezone.now()
        order.save(update_fields=["status", "assigned_to", "claimed_at"])
        _notify(order.child, Notification.Kind.SHOPPING, "Parent is shopping your cart", f"{fulfiller.display_name} selected order #{order.pk} to purchase.")
        _audit(fulfiller, order.child, "shopping_order_claimed", f"Shopping order #{order.pk} claimed.")
    messages.success(request, f"You selected {order.child.display_name}'s shopping order.")
    return redirect(f"/?child={order.child.pk}")


@login_required
@require_POST
def fulfillment_cancel(request, pk):
    fulfiller = _fulfiller(request)
    if fulfiller is None:
        return redirect("dashboard")
    with transaction.atomic():
        order = get_object_or_404(
            ShoppingOrder.objects.select_for_update().select_related("child", "reservation_ledger"),
            pk=pk,
        )
        if order.status not in [ShoppingOrder.Status.SUBMITTED, ShoppingOrder.Status.CLAIMED]:
            messages.error(request, "Only waiting shopping orders can be canceled.")
            return redirect(f"/?child={order.child.pk}")
        wallet = Wallet.objects.select_for_update().get(child=order.child)
        Wallet.objects.filter(pk=wallet.pk).update(
            cash_cents=F("cash_cents") + order.held_cash_cents,
            spending_cents=F("spending_cents") + order.held_spending_cents,
        )
        ledger = order.reservation_ledger
        if ledger and ledger.status == LedgerRequest.Status.PENDING:
            ledger.status = LedgerRequest.Status.DECLINED
            ledger.reviewed_by = fulfiller
            ledger.reviewed_at = timezone.now()
            ledger.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        order.status = ShoppingOrder.Status.CANCELED
        order.assigned_to = fulfiller
        order.parent_note = request.POST.get("parent_note", "")[:240]
        order.canceled_at = timezone.now()
        order.save(update_fields=["status", "assigned_to", "parent_note", "canceled_at"])
        _notify(order.child, Notification.Kind.SHOPPING, "Shopping order canceled", f"Order #{order.pk} was canceled and ${order.reserved_total_cents / 100:.2f} returned to your Cash App balance.")
        _audit(fulfiller, order.child, "shopping_order_canceled", f"Shopping order #{order.pk} canceled; ${order.reserved_total_cents / 100:.2f} released.", ledger=ledger)
    messages.info(request, "Order canceled and reserved cash returned.")
    return redirect(f"/?child={order.child.pk}")


@login_required
@require_POST
def fulfillment_purchase(request, pk):
    fulfiller = _fulfiller(request)
    if fulfiller is None:
        return redirect("dashboard")
    form = ShoppingFulfillmentForm(request.POST)
    order = get_object_or_404(ShoppingOrder.objects.select_related("child"), pk=pk)
    if not form.is_valid():
        messages.error(request, "Enter the confirmed amount paid before marking the order purchased.")
        return redirect(f"/?child={order.child.pk}")
    final_total = _cents(form.cleaned_data["final_amount"])
    with transaction.atomic():
        order = ShoppingOrder.objects.select_for_update().select_related("child", "reservation_ledger").get(pk=pk)
        if order.status not in [ShoppingOrder.Status.SUBMITTED, ShoppingOrder.Status.CLAIMED]:
            messages.error(request, "That order is no longer waiting for purchase.")
            return redirect(f"/?child={order.child.pk}")
        wallet = Wallet.objects.select_for_update().get(child=order.child)
        reserved_total = order.reserved_total_cents
        final_cash = order.held_cash_cents
        final_spending = order.held_spending_cents
        if final_total > reserved_total:
            extra = final_total - reserved_total
            sources = _cash_sources(wallet, extra)
            if sources is None:
                messages.error(request, "The confirmed total is higher and the child does not have enough available cash for the difference.")
                return redirect(f"/?child={order.child.pk}")
            extra_cash, extra_spending = sources
            Wallet.objects.filter(pk=wallet.pk).update(
                cash_cents=F("cash_cents") - extra_cash,
                spending_cents=F("spending_cents") - extra_spending,
            )
            final_cash += extra_cash
            final_spending += extra_spending
        elif final_total < reserved_total:
            final_cash = min(order.held_cash_cents, final_total)
            final_spending = final_total - final_cash
            Wallet.objects.filter(pk=wallet.pk).update(
                cash_cents=F("cash_cents") + order.held_cash_cents - final_cash,
                spending_cents=F("spending_cents") + order.held_spending_cents - final_spending,
            )
        ledger = order.reservation_ledger
        if ledger:
            ledger.description = f"Shopping order purchased: ${final_total / 100:.2f}"
            ledger.cash_delta_cents = -final_cash
            ledger.spending_delta_cents = -final_spending
            ledger.status = LedgerRequest.Status.APPROVED
            ledger.reviewed_by = fulfiller
            ledger.reviewed_at = timezone.now()
            ledger.save(
                update_fields=[
                    "description",
                    "cash_delta_cents",
                    "spending_delta_cents",
                    "status",
                    "reviewed_by",
                    "reviewed_at",
                ]
            )
        order.status = ShoppingOrder.Status.PURCHASED
        order.assigned_to = fulfiller
        order.held_cash_cents = final_cash
        order.held_spending_cents = final_spending
        order.final_total_cents = final_total
        order.parent_note = form.cleaned_data.get("parent_note", "")
        order.purchased_at = timezone.now()
        order.save(
            update_fields=[
                "status",
                "assigned_to",
                "held_cash_cents",
                "held_spending_cents",
                "final_total_cents",
                "parent_note",
                "purchased_at",
            ]
        )
        _notify(order.child, Notification.Kind.SHOPPING, "Order purchased", f"Your parent purchased order #{order.pk} for ${final_total / 100:.2f}.")
        _audit(fulfiller, order.child, "shopping_order_purchased", f"Shopping order #{order.pk} purchased for ${final_total / 100:.2f}.", ledger=ledger)
    messages.success(request, "Purchase recorded and the child's Cash App balance finalized.")
    return redirect(f"/?child={order.child.pk}")


@login_required
@require_POST
def fulfillment_delivered(request, pk):
    fulfiller = _fulfiller(request)
    if fulfiller is None:
        return redirect("dashboard")
    order = get_object_or_404(ShoppingOrder.objects.select_related("child"), pk=pk)
    if order.status != ShoppingOrder.Status.PURCHASED:
        messages.error(request, "Only purchased orders can be marked delivered.")
        return redirect(f"/?child={order.child.pk}")
    order.status = ShoppingOrder.Status.DELIVERED
    order.delivered_at = timezone.now()
    order.save(update_fields=["status", "delivered_at"])
    _notify(order.child, Notification.Kind.SHOPPING, "Shopping delivered", f"Order #{order.pk} was marked delivered. Enjoy!")
    _audit(fulfiller, order.child, "shopping_order_delivered", f"Shopping order #{order.pk} delivered.")
    messages.success(request, "Order marked delivered.")
    return redirect(f"/?child={order.child.pk}")


@login_required
@require_POST
def update_family_settings(request):
    guardian = _guardian(request)
    if guardian is None:
        return redirect("dashboard")
    settings_record = FamilySettings.load()
    form = FamilySettingsForm(request.POST, instance=settings_record)
    if not form.is_valid():
        messages.error(request, "Enter a valid token exchange rate.")
        return redirect(f"/?child={request.POST.get('child_id', '')}")
    settings_record = form.save(commit=False)
    settings_record.updated_by = guardian
    settings_record.save()
    _audit(guardian, None, "exchange_rate_updated", str(settings_record))
    messages.success(request, f"Wallet exchange rate updated: {settings_record}.")
    return redirect(f"/?child={request.POST.get('child_id', '')}")


@login_required
@require_POST
def guardian_communication_schedule(request):
    guardian = _guardian(request)
    child = get_object_or_404(Profile, pk=request.POST.get("child_id"), role=Profile.Role.CHILD)
    form = CommunicationScheduleForm(request.POST)
    if guardian is None or not form.is_valid():
        messages.error(request, "Check the communication schedule details and try again.")
        return redirect(f"/?child={child.pk}")
    schedule = form.save(commit=False)
    schedule.child = child
    schedule.created_by = guardian
    schedule.save()
    start = schedule.start_time.strftime("%I:%M %p").lstrip("0")
    end = schedule.end_time.strftime("%I:%M %p").lstrip("0")
    description = f"{schedule.get_feature_display()} locked {schedule.days_display} from {start} to {end}."
    _audit(guardian, child, "communication_schedule_created", description)
    messages.success(request, f"Communication schedule saved for {child.display_name}.")
    return redirect(f"/?child={child.pk}")


@login_required
@require_POST
def guardian_toggle_communication_schedule(request, pk):
    guardian = _guardian(request)
    schedule = get_object_or_404(CommunicationSchedule, pk=pk)
    if guardian is None:
        return redirect("dashboard")
    schedule.enabled = not schedule.enabled
    schedule.save(update_fields=["enabled"])
    action = "enabled" if schedule.enabled else "paused"
    _audit(guardian, schedule.child, f"communication_schedule_{action}", schedule.get_feature_display())
    messages.info(request, f"{schedule.get_feature_display()} schedule {action}.")
    return redirect(f"/?child={schedule.child.pk}")


@login_required
@require_POST
def guardian_remove_communication_schedule(request, pk):
    guardian = _guardian(request)
    schedule = get_object_or_404(CommunicationSchedule, pk=pk)
    if guardian is None:
        return redirect("dashboard")
    child = schedule.child
    description = schedule.get_feature_display()
    schedule.delete()
    _audit(guardian, child, "communication_schedule_deleted", description)
    messages.info(request, "Communication schedule deleted.")
    return redirect(f"/?child={child.pk}")


@login_required
@require_POST
def guardian_discover_schedule(request):
    manager = _video_manager(request)
    if manager is None:
        return redirect("dashboard")
    child = get_object_or_404(Profile, pk=request.POST.get("child_id"), role=Profile.Role.CHILD)
    form = DiscoverScheduleForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Check the Discover schedule details and try again.")
        return redirect(f"/?child={child.pk}#parent-video-library")
    schedule = form.save(commit=False)
    schedule.child = child
    schedule.created_by = manager
    schedule.save()
    start = schedule.start_time.strftime("%I:%M %p").lstrip("0")
    end = schedule.end_time.strftime("%I:%M %p").lstrip("0")
    description = f"Discover locked {schedule.days_display} from {start} to {end}."
    _audit(manager, child, "discover_schedule_created", description)
    messages.success(request, f"Discover screen-time schedule saved for {child.display_name}.")
    return redirect(f"/?child={child.pk}#parent-video-library")


@login_required
@require_POST
def guardian_toggle_discover_schedule(request, pk):
    manager = _video_manager(request)
    if manager is None:
        return redirect("dashboard")
    schedule = get_object_or_404(DiscoverSchedule, pk=pk)
    schedule.enabled = not schedule.enabled
    schedule.save(update_fields=["enabled"])
    action = "enabled" if schedule.enabled else "paused"
    _audit(manager, schedule.child, f"discover_schedule_{action}", "Discover viewing hours")
    messages.info(request, f"Discover schedule {action}.")
    return redirect(f"/?child={schedule.child.pk}#parent-video-library")


@login_required
@require_POST
def guardian_remove_discover_schedule(request, pk):
    manager = _video_manager(request)
    if manager is None:
        return redirect("dashboard")
    schedule = get_object_or_404(DiscoverSchedule, pk=pk)
    child = schedule.child
    schedule.delete()
    _audit(manager, child, "discover_schedule_deleted", "Discover viewing hours")
    messages.info(request, "Discover schedule deleted.")
    return redirect(f"/?child={child.pk}#parent-video-library")


@login_required
@require_POST
def acknowledge_rule(request, model, pk):
    child = _profile(request)
    if child.role != Profile.Role.CHILD:
        return redirect("dashboard")
    if model == "house_rule":
        rule = get_object_or_404(_current_house_rules(), pk=pk)
        RuleAcknowledgement.objects.get_or_create(child=child, house_rule=rule)
    elif model == "child_rule":
        rule = get_object_or_404(_current_child_rules(child), pk=pk)
        RuleAcknowledgement.objects.get_or_create(child=child, child_rule=rule)
    else:
        return redirect("dashboard")
    messages.success(request, "Thanks for confirming that you understand this rule.")
    return _child_destination(request)


@login_required
@require_POST
def read_notifications(request):
    child = _profile(request)
    if child.role == Profile.Role.CHILD:
        visible_notice_ids = list(
            child.notifications.filter(read_at__isnull=True).values_list("pk", flat=True)[:10]
        )
        child.notifications.filter(pk__in=visible_notice_ids).update(read_at=timezone.now())
    return redirect("dashboard")


@login_required
@require_POST
def dad_approve_schedule(request):
    dad = _dad(request)
    child = get_object_or_404(Profile, pk=request.POST.get("child_id"), role=Profile.Role.CHILD)
    if dad is None:
        return redirect(f"/?child={child.pk}")
    try:
        day = date.fromisoformat(request.POST.get("day", ""))
    except ValueError:
        messages.error(request, "Select a valid schedule date to publish.")
        return redirect(f"/?child={child.pk}")
    entries = child.schedule_events.filter(day=day)
    if not entries.exists():
        messages.error(request, "Add at least one event before approving this day's schedule.")
        return redirect(f"/?child={child.pk}")
    entries.update(approved_by=dad, approved_at=timezone.now())
    messages.success(request, f"{child.display_name}'s schedule for {day:%B} {day.day} is approved for release on that day.")
    return redirect(f"/?child={child.pk}")


@login_required
@require_POST
def guardian_lockdown(request):
    guardian = _guardian(request)
    child = get_object_or_404(Profile, pk=request.POST.get("child_id"), role=Profile.Role.CHILD)
    if guardian is None:
        return redirect("dashboard")
    child.refresh_grounding()
    locked = request.POST.get("action") == "lock"
    form = GroundingForm(request.POST)
    if locked and not form.is_valid():
        messages.error(request, "Please check the Grounded Mode reason and scheduled lift time.")
        return redirect(f"/?child={child.pk}")
    child.grounded = locked
    child.grounded_reason = form.cleaned_data.get("reason", "").strip() if locked else ""
    child.grounded_by = guardian if locked else None
    child.grounded_at = timezone.now() if locked else None
    child.grounded_until = form.cleaned_data.get("lift_at") if locked else None
    child.save(update_fields=["grounded", "grounded_reason", "grounded_by", "grounded_at", "grounded_until"])
    if locked:
        BehaviorNote.objects.create(
            child=child,
            issued_by=guardian,
            title="Grounded Mode issued",
            note=child.grounded_reason or "Grounded Mode was issued.",
            scheduled_lift_at=child.grounded_until,
        )
        _notify(child, Notification.Kind.GROUNDED, "Grounded Mode activated", child.grounded_reason or "Your parent activated Grounded Mode.")
        _audit(guardian, child, "grounded_mode_activated", child.grounded_reason or "Grounded Mode activated.")
        messages.success(request, f"{child.display_name} is now in Grounded Mode. Balances and rewards are locked.")
    else:
        _notify(child, Notification.Kind.GROUNDED, "Grounded Mode lifted", "Your rewards and wallet are available again.")
        _audit(guardian, child, "grounded_mode_lifted", "Grounded Mode lifted.")
        messages.success(request, f"{child.display_name}'s Grounded Mode has been lifted.")
    return redirect(f"/?child={child.pk}")


@login_required
@require_POST
def guardian_remove_behavior_note(request, pk):
    guardian = _guardian(request)
    note = get_object_or_404(BehaviorNote.objects.select_related("child"), pk=pk)
    if guardian is None:
        return redirect("dashboard")
    child = note.child
    active_grounding_note = (
        note.title == "Grounded Mode issued"
        and child.grounded
        and child.grounded_at
        and abs(note.issued_at - child.grounded_at) <= timedelta(seconds=5)
    )
    description = note.title
    if active_grounding_note:
        child.grounded = False
        child.grounded_reason = ""
        child.grounded_by = None
        child.grounded_at = None
        child.grounded_until = None
        child.save(update_fields=["grounded", "grounded_reason", "grounded_by", "grounded_at", "grounded_until"])
        _notify(child, Notification.Kind.GROUNDED, "Grounded Mode removed", "Your parent removed this restriction.")
    note.delete()
    _audit(guardian, child, "behavior_note_removed", description)
    messages.success(request, f"Removed the punishment record for {child.display_name}.")
    return redirect(f"/?child={child.pk}")


@login_required
@require_POST
def guardian_reverse_punishment(request, pk):
    guardian = _guardian(request)
    original = get_object_or_404(LedgerRequest.objects.select_related("child"), pk=pk)
    if guardian is None:
        return redirect("dashboard")
    if not original.can_reverse_punishment:
        messages.error(request, "This punishment has already been removed or cannot be reversed.")
        return redirect(f"/?child={original.child.pk}")
    with transaction.atomic():
        original = LedgerRequest.objects.select_for_update().select_related("child").get(pk=pk)
        if not original.can_reverse_punishment:
            messages.error(request, "This punishment has already been removed.")
            return redirect(f"/?child={original.child.pk}")
        reversal = LedgerRequest.objects.create(
            child=original.child,
            requested_by=guardian,
            kind=LedgerRequest.Kind.REVERSAL,
            description=f"Punishment removed: {original.description}"[:160],
            token_delta=-original.token_delta,
            reversal_of=original,
        )
        reversal.approve(guardian)
        _audit(guardian, original.child, "punishment_reversed", reversal.description, ledger=reversal)
    messages.success(request, f"Returned {-original.token_delta} token{'s' if original.token_delta != -1 else ''} to {original.child.display_name}.")
    return redirect(f"/?child={original.child.pk}")


@login_required
@require_POST
def award_star(request):
    guardian = _guardian(request)
    child = get_object_or_404(Profile, pk=request.POST.get("child_id"), role=Profile.Role.CHILD)
    try:
        day = date.fromisoformat(request.POST.get("day", ""))
    except ValueError:
        day = timezone.localdate()
    if guardian is None or day > timezone.localdate():
        return redirect(f"/?child={child.pk}")
    child.refresh_grounding()
    if child.grounded:
        messages.error(request, "Grounded Mode is active. Stars and their token rewards are locked.")
        return redirect(f"/?child={child.pk}&month={day:%Y-%m}")
    with transaction.atomic():
        star, created = BehaviorStar.objects.get_or_create(child=child, day=day, defaults={"awarded_by": guardian})
        if not created:
            messages.info(request, f"{child.display_name} already has a star for that day.")
            return redirect(f"/?child={child.pk}&month={day:%Y-%m}")
        entry = LedgerRequest.objects.create(
            child=child,
            requested_by=guardian,
            kind=LedgerRequest.Kind.STAR,
            description=f"Good behavior star - {day:%B} {day.day}",
            token_delta=2,
            behavior_star=star,
        )
        entry.approve(guardian)
    messages.success(request, f"Star awarded to {child.display_name}! +2 tokens.")
    return redirect(f"/?child={child.pk}&month={day:%Y-%m}")


@login_required
@require_POST
def subscribe_push(request):
    guardian = _guardian(request)
    if guardian is None:
        return JsonResponse({"ok": False}, status=403)
    try:
        subscription = json.loads(request.body)
        keys = subscription["keys"]
        PushSubscription.objects.update_or_create(
            endpoint=subscription["endpoint"],
            defaults={"guardian": guardian, "p256dh": keys["p256dh"], "auth": keys["auth"], "active": True},
        )
    except (KeyError, TypeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "message": "Invalid notification subscription."}, status=400)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def guardian_award(request):
    guardian = _guardian(request)
    child = get_object_or_404(Profile, pk=request.POST.get("child_id"), role=Profile.Role.CHILD)
    form = AwardForm(request.POST)
    if guardian is None or not form.is_valid():
        messages.error(request, "Please enter a reason and valid award.")
        return redirect(f"/?child={child.pk}")
    child.refresh_grounding()
    if child.grounded:
        messages.error(request, "Grounded Mode is active. Unlock this account before adding rewards.")
        return redirect(f"/?child={child.pk}")
    if not form.cleaned_data["tokens"] and not form.cleaned_data["cash_amount"]:
        messages.error(request, "Add bonus tokens, direct wallet cash, or both.")
        return redirect(f"/?child={child.pk}")
    entry = LedgerRequest.objects.create(
        child=child,
        requested_by=guardian,
        kind=LedgerRequest.Kind.AWARD,
        description=form.cleaned_data["reason"],
        token_delta=form.cleaned_data["tokens"],
        cash_delta_cents=_cents(form.cleaned_data["cash_amount"]),
    )
    entry.approve(guardian)
    messages.success(request, f"Award added to {child.display_name}'s balance.")
    return redirect(f"/?child={child.pk}")


@login_required
@require_POST
def guardian_behavior_deduction(request):
    guardian = _guardian(request)
    child = get_object_or_404(Profile, pk=request.POST.get("child_id"), role=Profile.Role.CHILD)
    form = BehaviorDeductionForm(request.POST)
    if guardian is None or not form.is_valid():
        messages.error(request, "Please enter a reason and number of tokens to remove.")
        return redirect(f"/?child={child.pk}")
    child.refresh_grounding()
    if child.grounded:
        messages.error(request, "Grounded Mode is active. Unlock this account before changing its token balance.")
        return redirect(f"/?child={child.pk}")
    tokens = form.cleaned_data["tokens"]
    entry = LedgerRequest.objects.create(
        child=child,
        requested_by=guardian,
        kind=LedgerRequest.Kind.BEHAVIOR,
        description=f"Behavior deduction: {form.cleaned_data['reason']}",
        token_delta=-tokens,
    )
    entry.approve(guardian)
    messages.success(request, f"Removed {tokens} token{'s' if tokens != 1 else ''} from {child.display_name}.")
    return redirect(f"/?child={child.pk}")


@login_required
@require_POST
def dad_balance_adjustment(request):
    guardian = _guardian(request)
    child = get_object_or_404(Profile, pk=request.POST.get("child_id"), role=Profile.Role.CHILD)
    form = BalanceAdjustmentForm(request.POST)
    if guardian is None or not form.is_valid():
        messages.error(request, "Please enter a valid balance adjustment.")
        return redirect(f"/?child={child.pk}")
    cents = _cents(form.cleaned_data["cash_amount"])
    sign = 1 if form.cleaned_data["direction"] == BalanceAdjustmentForm.ADD else -1
    account = form.cleaned_data["account"]
    entry = LedgerRequest.objects.create(
        child=child,
        requested_by=guardian,
        kind=LedgerRequest.Kind.BALANCE,
        description=f"Cash App balance adjustment: {form.cleaned_data['reason']}",
        cash_delta_cents=sign * cents,
    )
    try:
        entry.approve(guardian)
    except ValidationError as error:
        entry.delete()
        messages.error(request, error.message)
        return redirect(f"/?child={child.pk}")
    messages.success(request, f"{child.display_name}'s wallet funds have been updated.")
    return redirect(f"/?child={child.pk}")


@login_required
@require_POST
def review_request(request, pk, decision):
    guardian = _guardian(request)
    entry = get_object_or_404(LedgerRequest, pk=pk)
    if guardian is None:
        return redirect("dashboard")
    if entry.kind == LedgerRequest.Kind.SHOPPING:
        messages.info(request, "Shopping orders are completed in the Fulfillment app.")
        return redirect(f"/?child={entry.child.pk}")
    if entry.requires_dad_approval and guardian.user.username.lower() != "dad":
        messages.error(request, "Only Dad can approve wallet-to-spending and spending requests.")
        return redirect(f"/?child={entry.child.pk}")
    try:
        if decision == "approve":
            entry.approve(guardian)
            if entry.kind == LedgerRequest.Kind.CHORE and not (entry.token_delta or entry.cash_delta_cents):
                messages.success(request, "Chore verified. Grounded Mode keeps the balance unchanged.")
            else:
                messages.success(request, "Request approved and balance updated.")
        else:
            entry.decline(guardian)
            if entry.kind == LedgerRequest.Kind.CHORE:
                if entry.child.grounded or not entry.token_delta:
                    messages.info(request, "Quest not verified. Grounded Mode keeps the balance unchanged.")
                else:
                    messages.info(request, "Quest not verified. Its listed tokens were removed from the child's balance.")
            else:
                messages.info(request, "Request declined.")
    except ValidationError as error:
        messages.error(request, error.message)
    return redirect(f"/?child={entry.child.pk}")
