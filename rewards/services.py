from datetime import time

from django.utils import timezone

from .models import Chore, Notification, Profile


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

MORNING_OPTIONAL_LIBRARY = [
    ("Make your bed", "Straighten blankets and pillows before 10:00 AM."),
    ("Dress yourself", "Pick out clothes and get dressed before 10:00 AM."),
]


def ensure_today_chores():
    children = list(Profile.objects.filter(role=Profile.Role.CHILD).order_by("display_name"))
    today = timezone.localdate()
    if not children:
        return
    offset = today.toordinal() % len(children)
    children_with_new_chores = set()
    for index, (title, instructions) in enumerate(CHORE_LIBRARY):
        child = children[(index + offset) % len(children)]
        _, created = Chore.objects.get_or_create(
            child=child,
            title=title,
            due_date=today,
            defaults={
                "instructions": instructions,
                "token_reward": 4,
            },
        )
        if created:
            children_with_new_chores.add(child.pk)
    for child in children:
        for title, instructions in MORNING_OPTIONAL_LIBRARY:
            _, created = Chore.objects.get_or_create(
                child=child,
                title=title,
                due_date=today,
                defaults={
                    "instructions": instructions,
                    "token_reward": 4,
                    "credit_deadline": time(10, 0),
                    "optional": True,
                },
            )
            if created:
                children_with_new_chores.add(child.pk)
    for child in children:
        if child.pk in children_with_new_chores:
            Notification.objects.create(
                recipient=child,
                kind=Notification.Kind.CHORE,
                title="Today's quests are ready",
                message="Open your quest board to earn tokens from today's chores.",
            )
