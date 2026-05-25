from django.contrib import admin

from .models import (
    BehaviorStar,
    BehaviorNote,
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
    ScheduleReminderDispatch,
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
        BehaviorNote,
        LedgerRequest,
        PushSubscription,
        ReminderDispatch,
        ScheduleReminderDispatch,
    ]
)
