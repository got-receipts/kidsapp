from django.contrib import admin

from .models import (
    BehaviorStar,
    ChildRule,
    Chore,
    DailyScheduleEvent,
    Grade,
    GrowthGoal,
    HouseRule,
    LedgerRequest,
    Profile,
    PushSubscription,
    ReminderDispatch,
    SavingsGoal,
    StoreItem,
    Wallet,
)

admin.site.register(
    [
        Profile,
        Wallet,
        SavingsGoal,
        DailyScheduleEvent,
        ChildRule,
        HouseRule,
        Grade,
        Chore,
        GrowthGoal,
        StoreItem,
        BehaviorStar,
        LedgerRequest,
        PushSubscription,
        ReminderDispatch,
    ]
)
