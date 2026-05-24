# Family Circle

Family Circle is an installable iPhone-friendly family rewards PWA backed by Django and PostgreSQL. KJ, Astoria, and Saphira each have a child account. Dad, Mom, and GG have guardian accounts that share approval access without using age-related wording.

This is private family software. All rights reserved; it is not intended for redistribution.

## What Is Included

- Separate authenticated child and guardian views.
- School grades, chores, things-to-improve goals, a token store, and cash balances.
- Guardian approval for chore rewards, goal rewards, store spending, token conversion, and cash-out requests.
- Twelve rotating daily chores divided among the three children, with token credit available only before 7:00 PM Eastern.
- A live child-facing 7:00 PM quest countdown plus separate checked and guardian-verified progress bars.
- A daily good-behavior star calendar; each awarded star adds 2 tokens.
- Opt-in guardian push reminders to award stars after 7:30 PM and an account ledger showing spending and rewards.
- A daily animated child check-in summarizing newly earned stars/tokens, open quests, and the next reward target.
- Guardian-managed daily schedules, personal rules, and house rules shown in each child's morning briefing and daily dashboard.
- Experience rewards including museum, park, Hoffman's Playland, Lake George trips, and a Great Escape grand prize.
- In-app Savings and Spending balances with Dad-only recorded balance corrections and approval of withdrawals/transfers.
- Unverified checked quests create recorded token penalties; token balances may go below zero while internal Savings and Spending remain overdraft-protected.
- A separate child wallet page with large preset buttons and a custom amount option for token conversions, spending transfers, and cash requests.
- Child-created savings goals with animated progress based on their internal Savings balance.
- Atomic ledger-backed balance updates so approvals from multiple devices remain consistent.
- PWA manifest and service worker that cache only public app assets, not private dashboard data.
- Selectable light/dark themes, a kid-focused adventure-board layout, and iPhone/iPad home-screen support in portrait or landscape.
- A visible footer carrying the private-use notice and configurable app version (`APP_VERSION`, currently `0.9.0`).
- Docker and Railway configuration with PostgreSQL via `DATABASE_URL`.

## Run Locally

Create a virtual environment using Python 3.13, install requirements, migrate, and create development starter accounts:

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
3. Set the variables shown in `.env.example`, especially a strong `SECRET_KEY` and `CSRF_TRUSTED_ORIGINS`. Set `INITIAL_CHILD_PASSWORD` and `INITIAL_GUARDIAN_PASSWORD` before the first deploy for secure starter logins.
4. Deploy. The container migrates the database, seeds the six accounts and starter store entries, then starts Gunicorn. If the two initial password variables were omitted on the first deploy, the app boots using the temporary password `password123` for all six seeded accounts so deployment does not fail.
5. Provide per-account password variables instead of the shared initial variables before the first account creation when each family member should begin with a different password. A future account-settings screen can support self-service password changes.

The initial usernames are `kj`, `astoria`, `saphira`, `dad`, `mom`, and `gg`.

Do not leave accounts using the fallback password on an online app. Replace the initial passwords with strong individual credentials before sharing the deployment URL.

## Money Safety Boundary

`Savings` and `Spending` are internal Family Circle ledger balances. The app does not debit a parent's bank account, hold funds, create a spendable virtual card, or issue an Apple Wallet payment card. Dad can record real-world money provided or withdrawn and the audit history keeps those corrections visible.

An Apple Wallet display pass or a real funded card can be considered later only through an appropriate pass-signing setup or regulated card/payment provider, with stronger authentication and parental controls.

## Star Reminder Notifications

Web push needs VAPID keys configured in Railway as `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, and `VAPID_CLAIMS_EMAIL`. Guardians then open the installed app and tap **Turn on 7:30 PM star reminders** on their dashboard.

Add a second Railway service from the same repository for scheduled reminders:

```text
Start command: python manage.py send_star_reminders
Cron schedule: */30 * * * *
```

Railway evaluates cron schedules in UTC. The command checks the configured `America/New_York` application timezone and sends once per calendar day only after 7:30 PM, so it remains correct when daylight saving time changes.

On iPhone, push notifications require installing the PWA from Safari using **Add to Home Screen**, then enabling notifications from inside the installed app.

## iPhone And iPad Installation

Open the Railway HTTPS URL in Safari, tap the Share button, then choose **Add to Home Screen**. The interface adapts for iPhone and iPad, including landscape use on iPad. Each device signs into the relevant account and reads the same online family data.
