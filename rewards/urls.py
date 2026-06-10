from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("messages/", views.messages_inbox, name="messages_inbox"),
    path("messages/<int:recipient_pk>/", views.message_thread, name="message_thread"),
    path("messages/attachment/<int:pk>/", views.message_attachment, name="message_attachment"),
    path("profile/photo/", views.update_profile_photo, name="update_profile_photo"),
    path("profile/photo/<int:pk>/", views.profile_photo, name="profile_photo"),
    path("calls/incoming/", views.incoming_call_status, name="incoming_call_status"),
    path("calls/start/<int:recipient_pk>/<str:call_type>/", views.start_family_call, name="start_family_call"),
    path("calls/<int:pk>/", views.call_room, name="call_room"),
    path("calls/<int:pk>/accept/", views.accept_family_call, name="accept_family_call"),
    path("calls/<int:pk>/decline/", views.decline_family_call, name="decline_family_call"),
    path("calls/<int:pk>/end/", views.end_family_call, name="end_family_call"),
    path("calls/<int:pk>/add-member/", views.add_call_member, name="add_call_member"),
    path("calls/<int:pk>/token/", views.call_token, name="call_token"),
    path("calls/<int:pk>/status/", views.call_status, name="call_status"),
    path("login/", views.FamilyLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("health/", views.health, name="health"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("notifications/subscribe/", views.subscribe_push, name="subscribe_push"),
    path("notifications/read/", views.read_notifications, name="read_notifications"),
    path("guardian/settings/calls/", views.update_family_call_settings, name="update_family_call_settings"),
    path("guardian/messages/<int:contact_pk>/toggle/", views.dad_toggle_hidden_message_contact, name="dad_toggle_hidden_message_contact"),
    path("guardian/communications/schedule/", views.guardian_communication_schedule, name="guardian_communication_schedule"),
    path("guardian/communications/<int:pk>/toggle/", views.guardian_toggle_communication_schedule, name="guardian_toggle_communication_schedule"),
    path("guardian/communications/<int:pk>/remove/", views.guardian_remove_communication_schedule, name="guardian_remove_communication_schedule"),
]
