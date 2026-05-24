from django.contrib import admin

from .models import (
    BehaviorStar,
    Chore,
    Grade,
    GrowthGoal,
    LedgerRequest,
    Profile,
    PushSubscription,
    ReminderDispatch,
    StoreItem,
    Wallet,
)

admin.site.register(
    [Profile, Wallet, Grade, Chore, GrowthGoal, StoreItem, BehaviorStar, LedgerRequest, PushSubscription, ReminderDispatch]
)
