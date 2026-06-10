# Family Circle

Family Circle is now a private family communication web app backed by Django and PostgreSQL. It focuses on three things only:

- private family texting
- browser-based voice calls
- browser-based video chat

It is designed to work by URL on iPhone, iPad, desktop browsers, Android browsers, and Kindle Fire through the Silk Browser. A native Kindle app is not required.

This is private family software. All rights reserved; it is not intended for redistribution.

## Current Scope

- Authenticated accounts for KJ, Astoria, Saphira, Dad, Mom, and GG.
- A child-friendly communication home with large Text, Voice, and Video actions.
- Dad and GG control dashboards for family contacts, call settings, browser guidance, and child message/call schedules.
- Mom is a family contact for messaging, audio calls, and video calls; she does not receive parent controls.
- Private in-app Messages with profile photos, attachments, and family-only contact controls.
- LiveKit Cloud-powered one-to-one audio/video calling.
- Incoming call alerts across authenticated pages.
- Dad/GG controls for visible child contacts and message/call lock schedules.
- Browser push notification support where the device supports it.
- Light/dark theme, responsive layout, and footer versioning.
- Docker and Railway configuration with PostgreSQL via `DATABASE_URL`.

The old rewards, wallet, store, chores, grades, shopping, calendar, and Discover surfaces have been removed from the main app experience. Some backend code and historical migrations remain for now so existing databases can migrate safely while the communication app is stabilized.

## Versioning

The footer version is controlled by `APP_VERSION`. Update it for every deployed change, including fixes:

- Patch bump for fixes and small polish changes, such as `3.0.0` to `3.0.1`.
- Minor bump for new communication features or meaningful user-interface upgrades.

Keep `family_circle/settings.py`, `.env.example`, and the Railway `APP_VERSION` value aligned for each release.

Current version: `3.1.4`.

## Run Locally

Create a virtual environment using Python 3.13, install requirements, migrate, and create starter accounts:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DEBUG = "true"
python manage.py migrate
python manage.py seed_family --dev
python manage.py runserver
```

For `--dev`, all six accounts initially use `password123`; change passwords before any real use.

## Deploy To Railway

1. Push this folder to a Git repository and create a Railway project from it.
2. Add a Railway PostgreSQL database service and connect it to this app so `DATABASE_URL` is injected.
3. Set the variables shown in `.env.example`, especially a strong `SECRET_KEY`.
4. For this private installation, set `INITIAL_CHILD_PASSWORD=password123` and `INITIAL_GUARDIAN_PASSWORD=password123` before first deploy if you want the starter logins to match `ACCOUNT_LOGINS.md`.
5. Deploy. The container migrates the database, seeds the starter family accounts when needed, then starts Gunicorn.

The initial usernames are `kj`, `astoria`, `saphira`, `dad`, `mom`, and `gg`.

Do not leave accounts using the fallback password on an online app. Replace the initial passwords with strong individual credentials before sharing the deployment URL.

## Family Calling

Audio and video calls stay inside Family Circle and connect through LiveKit Cloud. Configure these Railway environment variables:

```text
LIVEKIT_WS_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret
FREE_CHILD_CALLS_PER_DAY=6
CHILD_CALL_TOKEN_COST=1
CALL_RECONNECT_MINUTES=5
```

`LIVEKIT_API_SECRET` must remain server-side. Django uses it only to issue short-lived participant tokens.

## Browser And Device Support

- iPhone and iPad: open the Railway HTTPS URL in Safari. Optionally use **Add to Home Screen**.
- Kindle Fire: open the same Railway HTTPS URL in the Silk Browser. No native app is required.
- Android: use Chrome or another modern browser.
- Desktop: use a modern browser.

For voice and video calls, each device must allow microphone and camera permissions when the browser asks. Push notifications depend on browser/device support; calling and messaging still work without push.
