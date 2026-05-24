from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.FamilyLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("health/", views.health, name="health"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("notifications/subscribe/", views.subscribe_push, name="subscribe_push"),
    path("chores/<int:pk>/start/", views.start_chore, name="start_chore"),
    path("chores/<int:pk>/submit/", views.submit_chore, name="submit_chore"),
    path("goals/<int:pk>/submit/", views.submit_goal, name="submit_goal"),
    path("store/<int:pk>/buy/", views.buy_item, name="buy_item"),
    path("wallet/", views.wallet_page, name="wallet_page"),
    path("wallet/convert/", views.request_conversion, name="request_conversion"),
    path("wallet/convert-to-savings/", views.request_tokens_to_savings, name="request_tokens_to_savings"),
    path("wallet/cashout/", views.request_cashout, name="request_cashout"),
    path("wallet/spending/", views.request_spending_transfer, name="request_spending_transfer"),
    path("wallet/send/", views.send_family_transfer, name="send_family_transfer"),
    path("wallet/goal/", views.save_savings_goal, name="save_savings_goal"),
    path("recap/dismiss/", views.dismiss_recap, name="dismiss_recap"),
    path("guardian/add/<str:model>/", views.guardian_create, name="guardian_create"),
    path("guardian/remove/<str:model>/<int:pk>/", views.guardian_remove, name="guardian_remove"),
    path("guardian/lockdown/", views.guardian_lockdown, name="guardian_lockdown"),
    path("guardian/star/", views.award_star, name="award_star"),
    path("guardian/award/", views.guardian_award, name="guardian_award"),
    path("guardian/deduct/", views.guardian_behavior_deduction, name="guardian_behavior_deduction"),
    path("guardian/balance/", views.dad_balance_adjustment, name="dad_balance_adjustment"),
    path("guardian/settings/google-calendar/", views.dad_google_calendar_settings, name="dad_google_calendar_settings"),
    path("guardian/review/<int:pk>/<str:decision>/", views.review_request, name="review_request"),
]
