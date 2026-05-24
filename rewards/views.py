import calendar
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, Sum, When
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    AwardForm,
    BalanceAdjustmentForm,
    BehaviorDeductionForm,
    CashOutForm,
    ChildRuleForm,
    ChoreForm,
    ConvertForm,
    DailyScheduleEventForm,
    FamilyTransferForm,
    GoalForm,
    GoogleCalendarSettingsForm,
    GradeForm,
    GroundingForm,
    HouseRuleForm,
    SavingsGoalForm,
    SpendingTransferForm,
    StoreItemForm,
    TokensToSavingsForm,
)
from .models import (
    BehaviorStar,
    ChildRule,
    Chore,
    DailyScheduleEvent,
    FamilySettings,
    GrowthGoal,
    HouseRule,
    LedgerRequest,
    Profile,
    PushSubscription,
    SavingsGoal,
    StoreItem,
    Wallet,
)
from .services import ensure_today_chores, public_google_calendar_events


class FamilyLoginView(LoginView):
    template_name = "rewards/login.html"
    redirect_authenticated_user = True


def health(request):
    return HttpResponse("ok", content_type="text/plain")


def service_worker(request):
    source = """const CACHE = 'family-circle-v1';
const CORE = ['/static/rewards/styles.css', '/static/rewards/app.js', '/static/rewards/icon.svg'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(CORE))); self.skipWaiting(); });
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('push', event => {
  const data = event.data ? event.data.json() : {title: 'Family Circle', body: 'Open Family Circle for an update.'};
  event.waitUntil(Promise.all([
    self.registration.showNotification(data.title, {body: data.body, icon: '/static/rewards/icon.svg', badge: '/static/rewards/icon.svg', data: {url: data.url || '/'}}),
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
    return get_object_or_404(Profile, user=request.user)


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
        messages.error(request, "Only Dad can change savings or spending balances.")
        return None
    return guardian


def _block_grounded_child(request, profile):
    if profile.role == Profile.Role.CHILD and profile.grounded:
        messages.error(request, "Grounded Mode is active. Money, tokens, rewards, and the store are locked.")
        return True
    return False


def _cents(amount):
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


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


@login_required
def dashboard(request):
    ensure_today_chores()
    profile = _profile(request)
    store_items = StoreItem.objects.filter(active=True).order_by(
        Case(
            When(category=StoreItem.Category.TREAT, then=0),
            When(category=StoreItem.Category.EXPERIENCE, then=1),
            When(category=StoreItem.Category.GRAND, then=2),
            output_field=IntegerField(),
        ),
        "token_cost",
    )
    if profile.can_view_family:
        can_manage = profile.is_guardian
        children = Profile.objects.filter(role=Profile.Role.CHILD).select_related("wallet")
        selected = children.filter(pk=request.GET.get("child")).first() or children.first()
        star_weeks, star_month, previous_month, next_month = _star_calendar(selected, request.GET.get("month")) if selected else ([], "", "", "")
        today = timezone.localdate()
        unstarred = children.exclude(behavior_stars__day=today)
        pending = LedgerRequest.objects.filter(status=LedgerRequest.Status.PENDING).select_related("child", "chore")
        family_settings = FamilySettings.objects.first()
        calendar_id = (
            family_settings.google_calendar_id if family_settings and family_settings.google_calendar_enabled
            else settings.GOOGLE_CALENDAR_ID if family_settings is None
            else ""
        )
        history = selected.ledger_requests.select_related("store_item", "reviewed_by").all()[:30] if selected else []
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
            "children": children,
            "selected": selected,
            "store_items": store_items,
            "pending": pending.exclude(kind=LedgerRequest.Kind.CHORE),
            "pending_chore_reviews": pending.filter(child=selected, kind=LedgerRequest.Kind.CHORE) if selected else [],
            "selected_chores": selected.chores.filter(due_date=today, optional=False).order_by("title") if selected else [],
            "selected_optional_chores": selected.chores.filter(due_date=today, optional=True).order_by("title") if selected else [],
            "selected_schedule": selected.schedule_events.filter(day__gte=today)[:20] if selected else [],
            "selected_rules": selected.specific_rules.filter(active=True) if selected else [],
            "selected_grades": selected.grades.order_by("-created_at")[:8] if selected else [],
            "selected_goals": selected.goals.order_by("-created_at")[:8] if selected else [],
            "house_rules": HouseRule.objects.filter(active=True),
            "history": history,
            "star_weeks": star_weeks,
            "star_month": star_month,
            "previous_month": previous_month,
            "next_month": next_month,
            "unstarred": unstarred,
            "star_reminder_due": can_manage and timezone.localtime().time() >= time(19, 30) and unstarred.exists(),
            "vapid_public_key": settings.VAPID_PUBLIC_KEY,
            "grade_form": GradeForm(),
            "chore_form": ChoreForm(),
            "goal_form": GoalForm(),
            "item_form": StoreItemForm(),
            "schedule_form": DailyScheduleEventForm(),
            "child_rule_form": ChildRuleForm(),
            "house_rule_form": HouseRuleForm(),
            "award_form": AwardForm(),
            "behavior_deduction_form": BehaviorDeductionForm(),
            "balance_form": BalanceAdjustmentForm(),
            "grounding_form": GroundingForm(),
            "dad_controls": can_manage and profile.user.username.lower() == "dad",
            "google_calendar_enabled": bool(calendar_id and settings.GOOGLE_CALENDAR_API_KEY),
            "google_api_key_configured": bool(settings.GOOGLE_CALENDAR_API_KEY),
            "google_calendar_form": GoogleCalendarSettingsForm(
                instance=family_settings,
                initial={
                    "google_calendar_enabled": bool(settings.GOOGLE_CALENDAR_ID),
                    "google_calendar_id": settings.GOOGLE_CALENDAR_ID,
                } if family_settings is None else None,
            ),
        }
        return render(request, "rewards/guardian_dashboard.html", context)
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
    recap_token_total = recap_entries.filter(token_delta__gt=0).aggregate(total=Sum("token_delta"))["total"] or 0
    recap_token_loss = -(recap_entries.filter(kind__in=[LedgerRequest.Kind.PENALTY, LedgerRequest.Kind.BEHAVIOR]).aggregate(total=Sum("token_delta"))["total"] or 0)
    recap_purchases = recap_entries.filter(kind=LedgerRequest.Kind.STORE).count()
    next_prize = store_items.filter(token_cost__gt=profile.wallet.tokens).order_by("token_cost").first()
    savings_goal = SavingsGoal.objects.filter(child=profile).first()
    today = timezone.localdate()
    context = {
        "profile": profile,
        "wallet": profile.wallet,
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
        "star_today": profile.behavior_stars.filter(day=timezone.localdate()).exists(),
        "goals": profile.goals.exclude(status=GrowthGoal.Status.COMPLETED).order_by("created_at"),
        "store_items": store_items,
        "savings_goal": savings_goal,
        "savings_goal_form": SavingsGoalForm(instance=savings_goal),
        "today": today,
        "quest_deadline": timezone.make_aware(datetime.combine(today, time(19, 0))),
        "morning_deadline": timezone.make_aware(datetime.combine(today, time(10, 0))),
        "today_schedule": profile.schedule_events.filter(day=today),
        "google_calendar_events": public_google_calendar_events(today),
        "specific_rules": profile.specific_rules.filter(active=True),
        "house_rules": HouseRule.objects.filter(active=True),
        "show_recap": profile.last_recap_day != timezone.localdate(),
        "recap_first_visit": since is None,
        "recap_star_count": recap_stars.count(),
        "recap_token_total": recap_token_total,
        "recap_token_loss": recap_token_loss,
        "recap_purchases": recap_purchases,
        "recap_tasks_left": today_chores.filter(status__in=[Chore.Status.OPEN, Chore.Status.IN_PROGRESS]).count(),
        "next_prize": next_prize,
        "tokens_to_next_prize": next_prize.token_cost - profile.wallet.tokens if next_prize else 0,
    }
    return render(request, "rewards/child_dashboard.html", context)


@login_required
def wallet_page(request):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    context = {
        "profile": profile,
        "wallet": profile.wallet,
        "ledger": profile.ledger_requests.all()[:20],
        "family_transfer_form": FamilyTransferForm(sender=profile),
    }
    return render(request, "rewards/wallet_page.html", context)


@login_required
@require_POST
def start_chore(request, pk):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    chore = get_object_or_404(Chore, pk=pk, child=profile, status=Chore.Status.OPEN)
    chore.status = Chore.Status.IN_PROGRESS
    chore.save(update_fields=["status"])
    if profile.grounded:
        messages.info(request, "You started it. Tap finished before the deadline so a guardian can verify your work.")
    else:
        messages.info(request, "You started it. Tap finished before 7 PM to earn your tokens!")
    return redirect("dashboard")


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
        messages.info(request, "Marked finished. It was after 7 PM, so this chore does not earn tokens today.")
        return redirect("dashboard")
    earns_rewards = not profile.grounded
    LedgerRequest.objects.create(
        child=profile,
        requested_by=profile,
        kind=LedgerRequest.Kind.CHORE,
        description=f"{'Completed chore' if earns_rewards else 'Grounded chore check'}: {chore.title}",
        token_delta=chore.token_reward if earns_rewards else 0,
        cash_delta_cents=chore.cash_reward_cents if earns_rewards else 0,
        chore=chore,
    )
    chore.status = Chore.Status.SUBMITTED
    chore.save(update_fields=["status"])
    if earns_rewards:
        messages.success(request, "Nice work. A guardian can now approve your chore reward.")
    else:
        messages.success(request, "Nice work. A guardian can verify your chore, but Grounded Mode adds no tokens.")
    return redirect("dashboard")


@login_required
@require_POST
def submit_goal(request, pk):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
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
    return redirect("dashboard")


@login_required
@require_POST
def buy_item(request, pk):
    profile = _profile(request)
    item = get_object_or_404(StoreItem, pk=pk, active=True)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    if profile.wallet.tokens < item.token_cost:
        messages.error(request, "You do not have enough tokens yet.")
        return redirect("dashboard")
    LedgerRequest.objects.create(
        child=profile,
        requested_by=profile,
        kind=LedgerRequest.Kind.STORE,
        description=f"Store request: {item.name}",
        token_delta=-item.token_cost,
        store_item=item,
    )
    messages.success(request, "Store request sent to your guardians.")
    return redirect("dashboard")


@login_required
@require_POST
def request_conversion(request):
    profile = _profile(request)
    form = ConvertForm(request.POST)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    if not form.is_valid():
        messages.error(request, "Conversions must be in 10 cent increments.")
        return redirect("wallet_page")
    cents = _cents(form.cleaned_data["cash_amount"])
    if cents > profile.wallet.cash_cents:
        messages.error(request, "That is more than your available cash balance.")
        return redirect("wallet_page")
    tokens = cents // 10
    LedgerRequest.objects.create(
        child=profile,
        requested_by=profile,
        kind=LedgerRequest.Kind.CONVERT,
        description=f"Convert ${cents / 100:.2f} to {tokens} tokens",
        token_delta=tokens,
        cash_delta_cents=-cents,
    )
    messages.success(request, "Savings-to-Tokens request sent to Dad. The rate is $1 for 10 tokens.")
    return redirect("wallet_page")


@login_required
@require_POST
def request_tokens_to_savings(request):
    profile = _profile(request)
    form = TokensToSavingsForm(request.POST)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    if not form.is_valid():
        messages.error(request, "Conversions must be in 10 cent increments.")
        return redirect("wallet_page")
    cents = _cents(form.cleaned_data["cash_amount"])
    tokens = cents // 10
    if tokens > profile.wallet.tokens:
        messages.error(request, "You do not have enough Tokens for that Savings conversion.")
        return redirect("wallet_page")
    LedgerRequest.objects.create(
        child=profile,
        requested_by=profile,
        kind=LedgerRequest.Kind.CONVERT,
        description=f"Convert {tokens} tokens to ${cents / 100:.2f} savings",
        token_delta=-tokens,
        cash_delta_cents=cents,
    )
    messages.success(request, "Tokens-to-Savings request sent to Dad. The rate is 10 tokens for $1.")
    return redirect("wallet_page")


@login_required
@require_POST
def request_cashout(request):
    profile = _profile(request)
    form = CashOutForm(request.POST)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    if not form.is_valid():
        messages.error(request, "Please choose or enter an amount to request.")
        return redirect("wallet_page")
    cents = _cents(form.cleaned_data["cash_amount"])
    if cents > profile.wallet.cash_cents:
        messages.error(request, "That is more than your available cash balance.")
        return redirect("wallet_page")
    LedgerRequest.objects.create(
        child=profile,
        requested_by=profile,
        kind=LedgerRequest.Kind.CASH_OUT,
        description=f"Cash out ${cents / 100:.2f}",
        cash_delta_cents=-cents,
    )
    messages.success(request, "Cash-out request sent to Dad for review.")
    return redirect("wallet_page")


@login_required
@require_POST
def request_spending_transfer(request):
    profile = _profile(request)
    form = SpendingTransferForm(request.POST)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    if not form.is_valid():
        messages.error(request, "Please choose or enter an amount to move.")
        return redirect("wallet_page")
    cents = _cents(form.cleaned_data["cash_amount"])
    if cents > profile.wallet.cash_cents:
        messages.error(request, "That is more than your savings balance.")
        return redirect("wallet_page")
    LedgerRequest.objects.create(
        child=profile,
        requested_by=profile,
        kind=LedgerRequest.Kind.TRANSFER,
        description=f"Move ${cents / 100:.2f} from savings to spending",
        cash_delta_cents=-cents,
        spending_delta_cents=cents,
    )
    messages.success(request, "Your request to move money to spending was sent to Dad.")
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
        messages.error(request, "Choose a family member and enter an amount to send.")
        return redirect("wallet_page")
    recipient = form.cleaned_data["recipient_id"]
    if recipient.grounded:
        messages.error(request, "That family member is in Grounded Mode and cannot receive money right now.")
        return redirect("wallet_page")
    cents = _cents(form.cleaned_data["cash_amount"])
    with transaction.atomic():
        wallets = {
            wallet.child_id: wallet
            for wallet in Wallet.objects.select_for_update()
            .filter(child_id__in=[profile.pk, recipient.pk])
            .order_by("pk")
        }
        sender_wallet = wallets[profile.pk]
        recipient_wallet = wallets[recipient.pk]
        if cents > sender_wallet.spending_cents:
            messages.error(request, "You do not have enough in Spending to send that amount.")
            return redirect("wallet_page")
        Wallet.objects.filter(pk=sender_wallet.pk).update(spending_cents=F("spending_cents") - cents)
        Wallet.objects.filter(pk=recipient_wallet.pk).update(spending_cents=F("spending_cents") + cents)
        timestamp = timezone.now()
        LedgerRequest.objects.create(
            child=profile,
            requested_by=profile,
            counterparty=recipient,
            kind=LedgerRequest.Kind.GIFT,
            description=f"Sent ${cents / 100:.2f} to {recipient.display_name}",
            spending_delta_cents=-cents,
            status=LedgerRequest.Status.APPROVED,
            reviewed_at=timestamp,
        )
        LedgerRequest.objects.create(
            child=recipient,
            requested_by=profile,
            counterparty=profile,
            kind=LedgerRequest.Kind.GIFT,
            description=f"Received ${cents / 100:.2f} from {profile.display_name}",
            spending_delta_cents=cents,
            status=LedgerRequest.Status.APPROVED,
            reviewed_at=timestamp,
        )
    messages.success(request, f"You sent ${cents / 100:.2f} to {recipient.display_name}.")
    return redirect("wallet_page")


@login_required
@require_POST
def save_savings_goal(request):
    profile = _profile(request)
    if profile.can_view_family:
        return redirect("dashboard")
    if _block_grounded_child(request, profile):
        return redirect("dashboard")
    goal = SavingsGoal.objects.filter(child=profile).first()
    form = SavingsGoalForm(request.POST, instance=goal)
    if not form.is_valid():
        messages.error(request, "Please choose a goal name and a savings amount.")
        return redirect("dashboard")
    goal = form.save(commit=False)
    goal.child = profile
    goal.target_cents = _cents(form.cleaned_data["target_amount"])
    goal.save()
    messages.success(request, f"Your savings goal is set: {goal.name}!")
    return redirect("dashboard")


@login_required
@require_POST
def dismiss_recap(request):
    profile = _profile(request)
    if profile.role == Profile.Role.CHILD:
        profile.last_recap_at = timezone.now()
        profile.last_recap_day = timezone.localdate()
        profile.save(update_fields=["last_recap_at", "last_recap_day"])
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
        messages.success(request, "House rule added for everyone.")
        return redirect(f"/?child={request.POST.get('child_id', '')}")
    child = get_object_or_404(Profile, pk=request.POST.get("child_id"), role=Profile.Role.CHILD)
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
            record.cash_reward_cents = _cents(form.cleaned_data["cash_reward"])
            record.due_date = timezone.localdate()
            record.assigned_by = guardian
        if model in ["schedule", "child_rule"]:
            record.created_by = guardian
        record.save()
    labels = {"schedule": "Schedule event", "child_rule": "Personal rule"}
    messages.success(request, f"{labels.get(model, model.title())} added for {child.display_name}.")
    return redirect(f"/?child={child.pk}")


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
        record.delete()
    else:
        record.active = False
        record.save(update_fields=["active"])
    messages.info(request, "Item removed from the daily plan.")
    return redirect(f"/?child={selected_id}")


@login_required
@require_POST
def guardian_lockdown(request):
    guardian = _guardian(request)
    child = get_object_or_404(Profile, pk=request.POST.get("child_id"), role=Profile.Role.CHILD)
    if guardian is None:
        return redirect("dashboard")
    locked = request.POST.get("action") == "lock"
    form = GroundingForm(request.POST)
    if locked and not form.is_valid():
        messages.error(request, "Please check the Grounded Mode message.")
        return redirect(f"/?child={child.pk}")
    child.grounded = locked
    child.grounded_reason = form.cleaned_data.get("reason", "").strip() if locked else ""
    child.grounded_by = guardian if locked else None
    child.grounded_at = timezone.now() if locked else None
    child.save(update_fields=["grounded", "grounded_reason", "grounded_by", "grounded_at"])
    if locked:
        messages.success(request, f"{child.display_name} is now in Grounded Mode. Balances and rewards are locked.")
    else:
        messages.success(request, f"{child.display_name}'s Grounded Mode has been lifted.")
    return redirect(f"/?child={child.pk}")


@login_required
@require_POST
def dad_google_calendar_settings(request):
    dad = _dad(request)
    selected_id = request.POST.get("child_id", "")
    if dad is None:
        return redirect(f"/?child={selected_id}")
    family_settings = FamilySettings.objects.first()
    form = GoogleCalendarSettingsForm(request.POST, instance=family_settings)
    if not form.is_valid():
        messages.error(request, "Please enter a valid public Google Calendar ID.")
        return redirect(f"/?child={selected_id}#settings")
    record = form.save(commit=False)
    record.updated_by = dad
    record.save()
    messages.success(request, "Google Calendar display settings saved. Events are shown read-only.")
    return redirect(f"/?child={selected_id}#settings")


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
    if child.grounded:
        messages.error(request, "Grounded Mode is active. Unlock this account before adding rewards.")
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
    dad = _dad(request)
    child = get_object_or_404(Profile, pk=request.POST.get("child_id"), role=Profile.Role.CHILD)
    form = BalanceAdjustmentForm(request.POST)
    if dad is None or not form.is_valid():
        messages.error(request, "Please enter a valid balance adjustment.")
        return redirect(f"/?child={child.pk}")
    cents = _cents(form.cleaned_data["cash_amount"])
    sign = 1 if form.cleaned_data["direction"] == BalanceAdjustmentForm.ADD else -1
    account = form.cleaned_data["account"]
    entry = LedgerRequest.objects.create(
        child=child,
        requested_by=dad,
        kind=LedgerRequest.Kind.BALANCE,
        description=f"{account.title()} correction: {form.cleaned_data['reason']}",
        cash_delta_cents=sign * cents if account == BalanceAdjustmentForm.SAVINGS else 0,
        spending_delta_cents=sign * cents if account == BalanceAdjustmentForm.SPENDING else 0,
    )
    try:
        entry.approve(dad)
    except ValidationError as error:
        entry.delete()
        messages.error(request, error.message)
        return redirect(f"/?child={child.pk}")
    messages.success(request, f"{child.display_name}'s {account} balance has been updated.")
    return redirect(f"/?child={child.pk}")


@login_required
@require_POST
def review_request(request, pk, decision):
    guardian = _guardian(request)
    entry = get_object_or_404(LedgerRequest, pk=pk)
    if guardian is None:
        return redirect("dashboard")
    if entry.requires_dad_approval and guardian.user.username.lower() != "dad":
        messages.error(request, "Only Dad can approve savings and spending requests.")
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
