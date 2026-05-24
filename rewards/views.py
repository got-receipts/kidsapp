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
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import AwardForm, CashOutForm, ChoreForm, ConvertForm, GoalForm, GradeForm, StoreItemForm
from .models import BehaviorStar, Chore, GrowthGoal, LedgerRequest, Profile, PushSubscription, StoreItem
from .services import ensure_today_chores


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
        messages.error(request, "Only a guardian account can do that.")
        return None
    return profile


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
    store_items = StoreItem.objects.filter(active=True)
    if profile.is_guardian:
        children = Profile.objects.filter(role=Profile.Role.CHILD).select_related("wallet")
        selected = children.filter(pk=request.GET.get("child")).first() or children.first()
        star_weeks, star_month, previous_month, next_month = _star_calendar(selected, request.GET.get("month")) if selected else ([], "", "", "")
        today = timezone.localdate()
        unstarred = children.exclude(behavior_stars__day=today)
        context = {
            "profile": profile,
            "children": children,
            "selected": selected,
            "store_items": store_items,
            "pending": LedgerRequest.objects.filter(status=LedgerRequest.Status.PENDING).select_related("child"),
            "selected_chores": selected.chores.filter(due_date=today).order_by("title") if selected else [],
            "history": selected.ledger_requests.select_related("store_item", "reviewed_by").all()[:30] if selected else [],
            "star_weeks": star_weeks,
            "star_month": star_month,
            "previous_month": previous_month,
            "next_month": next_month,
            "unstarred": unstarred,
            "star_reminder_due": timezone.localtime().time() >= time(19, 30) and unstarred.exists(),
            "vapid_public_key": settings.VAPID_PUBLIC_KEY,
            "grade_form": GradeForm(),
            "chore_form": ChoreForm(),
            "goal_form": GoalForm(),
            "item_form": StoreItemForm(),
            "award_form": AwardForm(),
        }
        return render(request, "rewards/guardian_dashboard.html", context)
    today_chores = profile.chores.filter(due_date=timezone.localdate()).order_by("title")
    completed = today_chores.filter(status__in=[Chore.Status.SUBMITTED, Chore.Status.COMPLETED]).count()
    context = {
        "profile": profile,
        "wallet": profile.wallet,
        "grades": profile.grades.all().order_by("-created_at")[:8],
        "chores": today_chores,
        "chore_total": today_chores.count(),
        "chore_completed": completed,
        "chore_percent": round(completed / today_chores.count() * 100) if today_chores.count() else 0,
        "star_count": profile.behavior_stars.count(),
        "star_today": profile.behavior_stars.filter(day=timezone.localdate()).exists(),
        "goals": profile.goals.exclude(status=GrowthGoal.Status.COMPLETED).order_by("created_at"),
        "store_items": store_items,
        "ledger": profile.ledger_requests.all()[:10],
        "convert_form": ConvertForm(),
        "cashout_form": CashOutForm(),
    }
    return render(request, "rewards/child_dashboard.html", context)


@login_required
@require_POST
def start_chore(request, pk):
    profile = _profile(request)
    chore = get_object_or_404(Chore, pk=pk, child=profile, status=Chore.Status.OPEN)
    chore.status = Chore.Status.IN_PROGRESS
    chore.save(update_fields=["status"])
    messages.info(request, "You started it. Tap finished before 7 PM to earn your tokens!")
    return redirect("dashboard")


@login_required
@require_POST
def submit_chore(request, pk):
    profile = _profile(request)
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
    LedgerRequest.objects.create(
        child=profile,
        requested_by=profile,
        kind=LedgerRequest.Kind.CHORE,
        description=f"Completed chore: {chore.title}",
        token_delta=chore.token_reward,
        cash_delta_cents=chore.cash_reward_cents,
        chore=chore,
    )
    chore.status = Chore.Status.SUBMITTED
    chore.save(update_fields=["status"])
    messages.success(request, "Nice work. A guardian can now approve your chore reward.")
    return redirect("dashboard")


@login_required
@require_POST
def submit_goal(request, pk):
    profile = _profile(request)
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
    if profile.is_guardian:
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
    if profile.is_guardian:
        return redirect("dashboard")
    if not form.is_valid():
        messages.error(request, "Conversions must be in 10 cent increments.")
        return redirect("dashboard")
    cents = _cents(form.cleaned_data["cash_amount"])
    if cents > profile.wallet.cash_cents:
        messages.error(request, "That is more than your available cash balance.")
        return redirect("dashboard")
    tokens = cents // 10
    LedgerRequest.objects.create(
        child=profile,
        requested_by=profile,
        kind=LedgerRequest.Kind.CONVERT,
        description=f"Convert ${cents / 100:.2f} to {tokens} tokens",
        token_delta=tokens,
        cash_delta_cents=-cents,
    )
    messages.success(request, "Conversion requested. The rate is 10 tokens for each $1.")
    return redirect("dashboard")


@login_required
@require_POST
def request_cashout(request):
    profile = _profile(request)
    form = CashOutForm(request.POST)
    if profile.is_guardian or not form.is_valid():
        return redirect("dashboard")
    cents = _cents(form.cleaned_data["cash_amount"])
    if cents > profile.wallet.cash_cents:
        messages.error(request, "That is more than your available cash balance.")
        return redirect("dashboard")
    LedgerRequest.objects.create(
        child=profile,
        requested_by=profile,
        kind=LedgerRequest.Kind.CASH_OUT,
        description=f"Cash out ${cents / 100:.2f}",
        cash_delta_cents=-cents,
    )
    messages.success(request, "Cash-out request sent to Dad, Mom, and GG.")
    return redirect("dashboard")


@login_required
@require_POST
def guardian_create(request, model):
    guardian = _guardian(request)
    if guardian is None:
        return redirect("dashboard")
    child = get_object_or_404(Profile, pk=request.POST.get("child_id"), role=Profile.Role.CHILD)
    forms = {"grade": GradeForm, "chore": ChoreForm, "goal": GoalForm, "item": StoreItemForm}
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
        record.save()
    messages.success(request, f"{model.title()} added for {child.display_name}.")
    return redirect(f"/?child={child.pk}")


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
def review_request(request, pk, decision):
    guardian = _guardian(request)
    entry = get_object_or_404(LedgerRequest, pk=pk)
    if guardian is None:
        return redirect("dashboard")
    try:
        if decision == "approve":
            entry.approve(guardian)
            messages.success(request, "Request approved and balance updated.")
        else:
            entry.decline(guardian)
            messages.info(request, "Request declined.")
    except ValidationError as error:
        messages.error(request, error.message)
    return redirect(f"/?child={entry.child.pk}")
