from django.contrib import admin

from .models import Chore, Grade, GrowthGoal, LedgerRequest, Profile, StoreItem, Wallet

admin.site.register([Profile, Wallet, Grade, Chore, GrowthGoal, StoreItem, LedgerRequest])
