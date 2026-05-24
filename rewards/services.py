from datetime import time

from django.conf import settings
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


def teamup_calendar_url():
    family_settings = FamilySettings.objects.first()
    if family_settings is None:
        return settings.TEAMUP_CALENDAR_URL
    if family_settings.teamup_calendar_enabled:
        return family_settings.teamup_calendar_url
    return ""
