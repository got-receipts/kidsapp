import json
from datetime import datetime, time, timedelta
from urllib.parse import quote, urlencode
from urllib.request import urlopen

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .models import Chore, FamilySettings, Profile


CHORE_LIBRARY = [
    ("Clean your room", "Put away clothes and leave the floor clear."),
    ("Put away bedroom toys", "Return your toys to their homes."),
    ("Gather toys around the house", "Check shared rooms for toys."),
    ("Tidy the family toy bins", "Sort loose toys into their bins."),
    ("Finish your dinner", "Eat the dinner served unless a grown-up says otherwise."),
    ("Clear your dinner place", "Bring dishes to the kitchen after eating."),
    ("Wipe your dinner spot", "Leave your seat and table area neat."),
    ("Put away shoes and backpack", "Keep the entry area tidy."),
    ("Follow Dad's directions", "Listen and respond kindly today."),
    ("Follow GG's directions", "Listen and respond kindly today."),
    ("Quick living room tidy", "Help make shared spaces peaceful."),
    ("Bedtime reset", "Put away the items you used today."),
]


def ensure_today_chores():
    children = list(Profile.objects.filter(role=Profile.Role.CHILD).order_by("display_name"))
    today = timezone.localdate()
    if not children:
        return
    offset = today.toordinal() % len(children)
    for index, (title, instructions) in enumerate(CHORE_LIBRARY):
        child = children[(index + offset) % len(children)]
        Chore.objects.get_or_create(
            child=child,
            title=title,
            due_date=today,
            defaults={
                "instructions": instructions,
                "token_reward": 4,
            },
        )
    for child in children:
        Chore.objects.get_or_create(
            child=child,
            title="Make your bed",
            due_date=today,
            defaults={
                "instructions": "Straighten blankets and pillows before 10:00 AM.",
                "token_reward": 4,
                "credit_deadline": time(10, 0),
                "optional": True,
            },
        )


def public_google_calendar_events(day):
    family_settings = FamilySettings.objects.first()
    if family_settings is None:
        calendar_id = settings.GOOGLE_CALENDAR_ID
    else:
        calendar_id = family_settings.google_calendar_id if family_settings.google_calendar_enabled else ""
    api_key = settings.GOOGLE_CALENDAR_API_KEY
    if not calendar_id or not api_key:
        return []
    cache_key = f"google-calendar:{calendar_id}:{day:%Y-%m-%d}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    start = timezone.make_aware(datetime.combine(day, time.min)).isoformat()
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min)).isoformat()
    query = urlencode(
        {
            "key": api_key,
            "timeMin": start,
            "timeMax": end,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 20,
        }
    )
    url = f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id, safe='')}/events?{query}"
    try:
        with urlopen(url, timeout=5) as response:
            payload = json.load(response)
    except (OSError, ValueError):
        cache.set(cache_key, [], 60)
        return []
    events = []
    for event in payload.get("items", []):
        if event.get("status") == "cancelled":
            continue
        start_data = event.get("start", {})
        start_text = start_data.get("dateTime")
        display_time = ""
        if start_text:
            try:
                local_start = timezone.localtime(datetime.fromisoformat(start_text.replace("Z", "+00:00")))
                display_time = local_start.strftime("%I:%M %p").lstrip("0")
            except ValueError:
                display_time = ""
        events.append(
            {
                "title": event.get("summary", "Family event"),
                "details": event.get("location", ""),
                "time": display_time or "All day",
            }
        )
    cache.set(cache_key, events, 300)
    return events
