import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from rewards.models import GrowthGoal, HouseRule, Profile, StoreItem, Wallet
from rewards.services import ensure_today_chores


class Command(BaseCommand):
    help = "Create the initial Family Circle child and guardian accounts."

    def add_arguments(self, parser):
        parser.add_argument("--dev", action="store_true", help="Use development-only starter passwords.")

    def handle(self, *args, **options):
        accounts = [
            ("kj", "KJ", Profile.Role.CHILD, "KJ_PASSWORD", "INITIAL_CHILD_PASSWORD"),
            ("astoria", "Astoria", Profile.Role.CHILD, "ASTORIA_PASSWORD", "INITIAL_CHILD_PASSWORD"),
            ("saphira", "Saphira", Profile.Role.CHILD, "SAPHIRA_PASSWORD", "INITIAL_CHILD_PASSWORD"),
            ("dad", "Dad", Profile.Role.GUARDIAN, "DAD_PASSWORD", "INITIAL_GUARDIAN_PASSWORD"),
            ("mom", "Mom", Profile.Role.GUARDIAN, "MOM_PASSWORD", "INITIAL_GUARDIAN_PASSWORD"),
            ("gg", "GG", Profile.Role.GUARDIAN, "GG_PASSWORD", "INITIAL_GUARDIAN_PASSWORD"),
        ]
        missing_new_password = False
        children = []
        for username, display_name, role, specific_env, shared_env in accounts:
            password = os.getenv(specific_env) or os.getenv(shared_env)
            if options["dev"]:
                password = password or "password123"
            if not User.objects.filter(username=username).exists() and not password:
                missing_new_password = True
                continue
            user, created = User.objects.get_or_create(username=username)
            if created:
                user.set_password(password)
                user.save(update_fields=["password"])
            profile, _ = Profile.objects.update_or_create(
                user=user,
                defaults={"display_name": display_name, "role": role},
            )
            if role == Profile.Role.CHILD:
                Wallet.objects.get_or_create(child=profile)
                children.append(profile)
        if missing_new_password:
            raise CommandError(
                "Set INITIAL_CHILD_PASSWORD and INITIAL_GUARDIAN_PASSWORD (or account-specific password variables) before the first deploy."
            )
        self._starter_content(children)
        ensure_today_chores()
        self.stdout.write(self.style.SUCCESS("Family Circle accounts are ready: KJ, Astoria, Saphira, Dad, Mom and GG."))

    def _starter_content(self, children):
        house_rules = [
            ("Finish chores on time", "Complete daily chores before 7:00 PM to earn credit."),
            ("Listen to directions", "Follow directions from Dad, Mom, or GG for the day."),
            ("Use kindness", "Speak kindly and make safe, caring choices."),
        ]
        for title, details in house_rules:
            HouseRule.objects.get_or_create(title=title, defaults={"details": details})
        store = [
            ("Extra screen time", "Choose 30 bonus minutes.", 25, StoreItem.Category.TREAT),
            ("Pick dessert", "Choose the family dessert.", 35, StoreItem.Category.TREAT),
            ("Movie night choice", "Choose the next movie.", 60, StoreItem.Category.TREAT),
            ("Stay up later", "One weekend bedtime pass.", 80, StoreItem.Category.TREAT),
            ("Park adventure", "Plan a fun family park outing.", 120, StoreItem.Category.EXPERIENCE),
            ("Museum trip", "Explore a museum together.", 180, StoreItem.Category.EXPERIENCE),
            ("Hoffman's Playland trip", "A day of rides and play.", 300, StoreItem.Category.EXPERIENCE),
            ("Lake George beach day", "A day trip to the beach at Lake George.", 450, StoreItem.Category.EXPERIENCE),
            ("Lake George weekend", "A three-day Lake George adventure.", 1200, StoreItem.Category.EXPERIENCE),
            ("Great Escape grand prize", "A major-ticket amusement park adventure.", 2500, StoreItem.Category.GRAND),
        ]
        for name, description, cost, category in store:
            StoreItem.objects.get_or_create(
                name=name,
                defaults={"description": description, "token_cost": cost, "category": category},
            )
        for child in children:
            GrowthGoal.objects.get_or_create(
                child=child,
                title="Practice a kind response",
                status=GrowthGoal.Status.ACTIVE,
                defaults={"encouragement": "Tell us about a moment you handled well.", "token_reward": 10},
            )
