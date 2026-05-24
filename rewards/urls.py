from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.FamilyLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("health/", views.health, name="health"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("chores/<int:pk>/submit/", views.submit_chore, name="submit_chore"),
    path("goals/<int:pk>/submit/", views.submit_goal, name="submit_goal"),
    path("store/<int:pk>/buy/", views.buy_item, name="buy_item"),
    path("wallet/convert/", views.request_conversion, name="request_conversion"),
    path("wallet/cashout/", views.request_cashout, name="request_cashout"),
    path("guardian/add/<str:model>/", views.guardian_create, name="guardian_create"),
    path("guardian/award/", views.guardian_award, name="guardian_award"),
    path("guardian/review/<int:pk>/<str:decision>/", views.review_request, name="review_request"),
]
