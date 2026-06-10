from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from .models import CommunicationSchedule, FamilyCall, FamilyCallParticipant, FamilyMessage, FamilySettings, HiddenMessageContact, Profile, Wallet


class CommunicationAppTests(TestCase):
    def setUp(self):
        self.child_user = User.objects.create_user(username="kj", password="test")
        self.sibling_user = User.objects.create_user(username="astoria", password="test")
        self.dad_user = User.objects.create_user(username="dad", password="test")
        self.gg_user = User.objects.create_user(username="gg", password="test")
        self.mom_user = User.objects.create_user(username="mom", password="test")
        self.child = Profile.objects.create(user=self.child_user, display_name="KJ", role=Profile.Role.CHILD)
        self.sibling = Profile.objects.create(user=self.sibling_user, display_name="Astoria", role=Profile.Role.CHILD)
        self.dad = Profile.objects.create(user=self.dad_user, display_name="Dad", role=Profile.Role.GUARDIAN)
        self.gg = Profile.objects.create(user=self.gg_user, display_name="GG", role=Profile.Role.GUARDIAN)
        self.mom = Profile.objects.create(user=self.mom_user, display_name="Mom", role=Profile.Role.VIEWER)
        for child in [self.child, self.sibling]:
            Wallet.objects.create(child=child, tokens=20)

    def test_child_dashboard_is_communication_only(self):
        self.client.force_login(self.child_user)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Private family line")
        self.assertContains(response, "It is simpler now.")
        self.assertContains(response, reverse("messages_inbox"))
        self.assertContains(response, "Kindle Fire friendly")
        self.assertContains(response, reverse("message_thread", args=[self.dad.pk]))
        self.assertNotContains(response, "Wallet")
        self.assertNotContains(response, "Discover")
        self.assertNotContains(response, "Store")
        self.assertNotContains(response, "Quests")

    def test_guardian_dashboard_is_communication_control_room(self):
        self.client.force_login(self.dad_user)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Family communication control")
        self.assertContains(response, "Family Circle is now communication-only.")
        self.assertContains(response, "Family Contacts")
        self.assertContains(response, "Child Communication Controls")
        self.assertContains(response, "Kindle Fire")
        self.assertContains(response, "Calling Rules")
        self.assertNotContains(response, "Wallet Funds")
        self.assertNotContains(response, "Video Library")
        self.assertNotContains(response, "Guardian Actions")

    def test_mom_is_contact_only_without_child_controls(self):
        self.client.force_login(self.mom_user)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Family contact")
        self.assertContains(response, "Mom</strong>")
        self.assertContains(response, "Family Circle is now communication-only.")
        self.assertContains(response, "Family Contacts")
        self.assertContains(response, "messages, audio calls, and video calls")
        self.assertNotContains(response, "Child Communication Controls")
        self.assertNotContains(response, "Calling Rules")

    def test_old_app_surfaces_are_removed(self):
        self.client.force_login(self.child_user)

        for route_name, args in [
            ("child_section", ["chores"]),
            ("wallet_page", []),
            ("shopping_page", []),
            ("discover_page", []),
        ]:
            with self.assertRaises(NoReverseMatch):
                reverse(route_name, args=args)

        for path in ["/apps/chores/", "/wallet/", "/shopping/", "/discover/"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404)

    def test_child_hidden_contacts_are_removed_from_dashboard_and_messages(self):
        HiddenMessageContact.objects.create(child=self.child, contact=self.mom, hidden_by=self.dad)
        self.client.force_login(self.child_user)

        dashboard = self.client.get(reverse("dashboard"))
        inbox = self.client.get(reverse("messages_inbox"))

        self.assertNotContains(dashboard, "Mom")
        self.assertNotContains(inbox, "Mom")
        self.assertContains(dashboard, "Dad")

    def test_family_messages_still_send_and_mark_read(self):
        self.client.force_login(self.child_user)

        response = self.client.post(reverse("message_thread", args=[self.dad.pk]), {"body": "Can we talk?"})

        self.assertRedirects(response, reverse("message_thread", args=[self.dad.pk]))
        message = FamilyMessage.objects.get(sender=self.child, recipient=self.dad)
        self.assertEqual(message.body, "Can we talk?")

        self.client.force_login(self.dad_user)
        self.client.get(reverse("message_thread", args=[self.child.pk]))
        message.refresh_from_db()
        self.assertIsNotNone(message.read_at)

    def test_guardian_can_update_calling_rules(self):
        self.client.force_login(self.dad_user)

        response = self.client.post(
            reverse("update_family_call_settings"),
            {
                "child_id": self.child.pk,
                "free_child_calls_anytime_enabled": "on",
            },
        )

        self.assertRedirects(response, f"/?child={self.child.pk}")
        settings_record = FamilySettings.load()
        self.assertTrue(settings_record.free_child_calls_anytime_enabled)
        self.assertFalse(settings_record.free_calls_after_6pm_enabled)

    def test_guardian_can_add_message_and_call_lock_schedule(self):
        self.client.force_login(self.dad_user)

        response = self.client.post(
            reverse("guardian_communication_schedule"),
            {
                "child_id": self.child.pk,
                "feature": CommunicationSchedule.Feature.BOTH,
                "days": ["0", "1", "2", "3", "4"],
                "start_time": "20:00",
                "end_time": "07:00",
                "enabled": "on",
            },
        )

        self.assertRedirects(response, f"/?child={self.child.pk}")
        self.assertTrue(CommunicationSchedule.objects.filter(child=self.child, created_by=self.dad).exists())

    @override_settings(
        LIVEKIT_WS_URL="wss://family.livekit.cloud",
        LIVEKIT_API_KEY="key",
        LIVEKIT_API_SECRET="secret",
        FREE_CHILD_CALLS_PER_DAY=6,
        CHILD_CALL_TOKEN_COST=1,
    )
    def test_child_can_start_family_call_when_livekit_is_configured(self):
        self.client.force_login(self.child_user)

        response = self.client.post(reverse("start_family_call", args=[self.dad.pk, "audio"]))

        call = FamilyCall.objects.get(caller=self.child, recipient=self.dad)
        self.assertRedirects(response, reverse("call_room", args=[call.pk]), fetch_redirect_response=False)
        self.assertEqual(call.call_type, FamilyCall.Type.AUDIO)
        self.assertEqual(call.token_cost, 0)
        self.assertTrue(call.participants.filter(profile=self.child, status=FamilyCallParticipant.Status.JOINED).exists())
        self.assertTrue(call.participants.filter(profile=self.dad, status=FamilyCallParticipant.Status.INVITED).exists())

    @override_settings(
        LIVEKIT_WS_URL="wss://family.livekit.cloud",
        LIVEKIT_API_KEY="key",
        LIVEKIT_API_SECRET="secret",
    )
    def test_audio_call_room_has_audio_board_and_group_controls(self):
        call = FamilyCall.objects.create(caller=self.child, recipient=self.dad, call_type=FamilyCall.Type.AUDIO)
        FamilyCallParticipant.objects.create(call=call, profile=self.child, status=FamilyCallParticipant.Status.JOINED, invited_by=self.child)
        FamilyCallParticipant.objects.create(call=call, profile=self.dad, status=FamilyCallParticipant.Status.INVITED, invited_by=self.child)
        self.client.force_login(self.child_user)

        response = self.client.get(reverse("call_room", args=[call.pk]))

        self.assertContains(response, "Audio Board")
        self.assertContains(response, "data-toggle-speaker")
        self.assertContains(response, "Add Member")
        self.assertContains(response, "audio-call-board")
        self.assertContains(response, self.sibling.display_name)

    @override_settings(
        LIVEKIT_WS_URL="wss://family.livekit.cloud",
        LIVEKIT_API_KEY="key",
        LIVEKIT_API_SECRET="secret",
    )
    def test_child_can_add_member_to_audio_group_call(self):
        call = FamilyCall.objects.create(caller=self.child, recipient=self.dad, call_type=FamilyCall.Type.AUDIO, status=FamilyCall.Status.ACTIVE)
        FamilyCallParticipant.objects.create(call=call, profile=self.child, status=FamilyCallParticipant.Status.JOINED, invited_by=self.child)
        FamilyCallParticipant.objects.create(call=call, profile=self.dad, status=FamilyCallParticipant.Status.JOINED, invited_by=self.child)
        self.client.force_login(self.child_user)

        response = self.client.post(reverse("add_call_member", args=[call.pk]), {"profile_id": self.sibling.pk})

        self.assertRedirects(response, reverse("call_room", args=[call.pk]))
        self.assertTrue(call.participants.filter(profile=self.sibling, status=FamilyCallParticipant.Status.INVITED).exists())

    @override_settings(
        LIVEKIT_WS_URL="wss://family.livekit.cloud",
        LIVEKIT_API_KEY="key",
        LIVEKIT_API_SECRET="secret",
    )
    def test_invited_group_member_accepts_before_joining(self):
        call = FamilyCall.objects.create(caller=self.child, recipient=self.dad, call_type=FamilyCall.Type.AUDIO, status=FamilyCall.Status.ACTIVE)
        FamilyCallParticipant.objects.create(call=call, profile=self.child, status=FamilyCallParticipant.Status.JOINED, invited_by=self.child)
        FamilyCallParticipant.objects.create(call=call, profile=self.sibling, status=FamilyCallParticipant.Status.INVITED, invited_by=self.child)
        self.client.force_login(self.sibling_user)

        room = self.client.get(reverse("call_room", args=[call.pk]))
        self.assertContains(room, "Accept")
        self.assertNotContains(room, "data-livekit-call=\"join\"")

        response = self.client.post(reverse("accept_family_call", args=[call.pk]))

        self.assertRedirects(response, reverse("call_room", args=[call.pk]))
        self.assertTrue(call.participants.filter(profile=self.sibling, status=FamilyCallParticipant.Status.JOINED).exists())

    @override_settings(
        LIVEKIT_WS_URL="wss://family.livekit.cloud",
        LIVEKIT_API_KEY="key",
        LIVEKIT_API_SECRET="secret",
    )
    def test_video_call_room_keeps_video_controls_separate(self):
        call = FamilyCall.objects.create(caller=self.child, recipient=self.dad, call_type=FamilyCall.Type.VIDEO)
        FamilyCallParticipant.objects.create(call=call, profile=self.child, status=FamilyCallParticipant.Status.JOINED, invited_by=self.child)
        FamilyCallParticipant.objects.create(call=call, profile=self.dad, status=FamilyCallParticipant.Status.INVITED, invited_by=self.child)
        self.client.force_login(self.child_user)

        response = self.client.get(reverse("call_room", args=[call.pk]))

        self.assertContains(response, "Video Call")
        self.assertContains(response, "data-toggle-camera")
        self.assertNotContains(response, "data-toggle-speaker")
        self.assertNotContains(response, "Add Member")
