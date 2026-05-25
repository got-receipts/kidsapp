# Family Circle

Family Circle is an installable iPhone-friendly family rewards PWA backed by Django and PostgreSQL. KJ, Astoria, and Saphira each have a child account. Dad and GG manage the family tools; Mom has a read-only Family Viewer account for following progress and growth.

This is private family software. All rights reserved; it is not intended for redistribution.

## What Is Included

- Separate authenticated child, guardian, and read-only family-viewer views.
- School grades, chores, things-to-improve goals, a token/cash Family Store, and wallet balances.
- Guardian approval for completed chore tokens, goals, store redemptions when configured, and real-world spending records.
- Twelve rotating daily chores divided among the three children, with token credit available only before 7:00 PM Eastern.
- A live child-facing 7:00 PM quest countdown plus separate checked and guardian-verified progress bars.
- Optional daily Make your bed and Dress yourself bonus quests worth tokens only when completed before 10:00 AM.
- A daily good-behavior star calendar; each awarded star adds 2 tokens.
- Dad/GG behavior deductions with a confirmation popup, recorded reason, and token debt support.
- Child login notifications for chores, approvals, token rewards, rule updates, Grounded Mode, wallet changes, and store purchases, plus guardian reminder push notifications.
- A daily animated child check-in summarizing newly earned stars/tokens, open quests, and the next reward target.
- A native guardian-only Family Calendar where Dad drafts and approves dated schedules before children receive them.
- A dedicated House Rules manager with create, edit, pause, delete, consequence, and child acknowledgement support.
- Guardian-managed individual rules with consequences and optional expiration/removal times, visible only to the assigned child.
- Experience rewards including museum, park, Hoffman's Playland, Lake George trips, and a Great Escape grand prize.
- Parent-configured token exchange rates; tokens convert immediately and irreversibly into wallet cash.
- Wallet cash and spendable cash balances, parent-recorded real-world spending, and sibling cash transfers.
- Unverified checked quests create recorded token penalties; token balances may go below zero while wallet and spendable cash remain overdraft-protected.
- A child wallet for immediate token cash-outs, direct sibling token gifts, sibling cash payments, and in-person spending records.
- Child-created wallet goals with animated progress based on their wallet cash balance.
- A Mom Family Viewer dashboard showing grades, chore progress, stars, schedule, rules, and positive highlights without editing or financial controls.
- Inventory-aware Family Store items with token prices, cash prices, mixed prices, hidden/unlocked state, age limits, and optional redemption approval.
- Atomic ledger-backed balance updates and audit logs for reward and rule enforcement changes.
- PWA manifest and service worker that cache only public app assets, not private dashboard data.
- Selectable light/dark themes, a kid-focused adventure-board layout, and iPhone/iPad home-screen support in portrait or landscape.
- A connected-home emblem identity, iOS Home Screen icon assets, and role-aware launch sequence designed for iPhone and iPad.
- A visible footer carrying the private-use notice and configurable app version (`APP_VERSION`, currently `2.2.0`).
- Docker and Railway configuration with PostgreSQL via `DATABASE_URL`.

## Versioning

The footer version is controlled by `APP_VERSION`. Update it for every deployed change, including fixes:

- Patch bump for fixes and small polish changes, such as `2.1.0` to `2.1.1`.
- Minor bump for new app features or meaningful user-interface upgrades, such as `2.1.0` to `2.2.0`.

Keep `family_circle/settings.py`, `.env.example`, and the Railway `APP_VERSION` value aligned for each release.

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
3. Set the variables shown in `.env.example`, especially a strong `SECRET_KEY`. Railway-generated `*.up.railway.app` domains are trusted automatically for secure form submissions; set `CSRF_TRUSTED_ORIGINS` only when using a custom domain. For this private installation, set `INITIAL_CHILD_PASSWORD=password123` and `INITIAL_GUARDIAN_PASSWORD=password123` so the starter logins match `ACCOUNT_LOGINS.md`.
4. Deploy. The container migrates the database, seeds the six accounts and starter store entries, then starts Gunicorn. If the two initial password variables were omitted on the first deploy, the app boots using the temporary password `password123` for all six seeded accounts so deployment does not fail.
5. Provide per-account password variables instead of the shared initial variables before the first account creation when each family member should begin with a different password. A future account-settings screen can support self-service password changes.

Version `2.1.2` includes a one-time PostgreSQL login recovery migration: if an earlier database already contains any starter family account, deployment resets the six family login passwords to `password123` and restores missing starter profiles or child wallets. It runs only once during migration and does not overwrite passwords on later restarts.

For a deliberate future password repair after this migration has already run, execute the seed command once with password variables configured:

```text
python manage.py seed_family --reset-passwords
```

The initial usernames are `kj`, `astoria`, `saphira`, `dad`, `mom`, and `gg`.

Account access is deliberately different: Dad and GG are guardian accounts with family-management controls; Mom is a read-only **Family Viewer** account that can see progress but cannot approve, edit, lock accounts, change rewards, subscribe to action reminders, or access child balances.

Dad and GG use the **Guardian Actions** panel to open focused popup interfaces for rewards, behavior deductions, Grounded Mode, grades, chores, goals, schedules, rules, and store updates. Behavior deductions are audited in account history and may make a token balance negative. Grounded Mode supports a scheduled lift and records a behavior note that Mom can see in her read-only dashboard.

Do not leave accounts using the fallback password on an online app. Replace the initial passwords with strong individual credentials before sharing the deployment URL.

## Money Safety Boundary

`Wallet cash` and `Spendable cash` are internal Family Circle ledger balances. The app does not debit a parent's bank account, hold funds, create a spendable virtual card, or issue an Apple Wallet payment card. Parents define the rate for converting earned tokens into wallet cash. That conversion is immediate and one-way: cash cannot become tokens again. Parents can record money provided or spent, and children may share tokens or available spendable cash with siblings; each transfer is audited.

An Apple Wallet display pass or a real funded card can be considered later only through an appropriate pass-signing setup or regulated card/payment provider, with stronger authentication and parental controls.

## Guardian Reminder Notifications

Web push needs VAPID keys configured in Railway as `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, and `VAPID_CLAIMS_EMAIL`. Dad or GG receives an in-app prompt to enable reminders, or can tap **Turn on reminders** on the dashboard later.

Add a second Railway service from the same repository for scheduled reminders:

```text
Start command: python manage.py send_star_reminders
Cron schedule: */30 * * * *
```

Railway evaluates cron schedules in UTC. The command checks the configured `America/New_York` application timezone and sends the star reminder once per day after 7:30 PM and the schedule-planning reminder once per day after 9:00 PM, so it remains correct when daylight saving time changes.

On iPhone, push notifications require installing the PWA from Safari using **Add to Home Screen**, then enabling notifications from inside the installed app.

## Family Calendar Publishing

The family schedule is managed entirely inside Family Circle. Dad can open **Family Calendar** on the guardian dashboard, queue events for future dates, and approve a child's day once the plan is ready. Dad and GG see the upcoming event queue; GG cannot create or publish events.

The expected routine is for Dad to prepare and approve the next day's schedule around 9:00 PM. Events may be drafted and approved in advance, but a child sees only approved events assigned to that child on the current day. No external calendar link or public calendar configuration is required.

## Grounded Mode

Dad or GG can activate **Grounded Mode** for an individual child from the guardian dashboard, optionally adding a scheduled lift time. The restriction lifts automatically on the first app request after that time is reached, or can be removed manually. The child receives an acknowledgement-only popup at dashboard entry, can continue completing chores for verification, and cannot see balances or use rewards and spending while locked. Mom can see the resulting behavior note without being granted action controls.

## iPhone And iPad Installation

Open the Railway HTTPS URL in Safari, tap the Share button, then choose **Add to Home Screen**. The interface adapts for iPhone and iPad, including landscape use on iPad. Each device signs into the relevant account and reads the same online family data.
