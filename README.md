# Family Circle

Family Circle is an installable iPhone-friendly family rewards PWA backed by Django and PostgreSQL. KJ, Astoria, and Saphira each have a child account. Dad, Mom, and GG have guardian accounts that share approval access without using age-related wording.

## What Is Included

- Separate authenticated child and guardian views.
- School grades, chores, things-to-improve goals, a token store, and cash balances.
- Guardian approval for chore rewards, goal rewards, store spending, token conversion, and cash-out requests.
- Atomic ledger-backed balance updates so approvals from multiple devices remain consistent.
- PWA manifest and service worker that cache only public app assets, not private dashboard data.
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

For `--dev`, all six accounts initially use `FamilyCircle123!`; change passwords before any real use.

## Deploy To Railway

1. Push this folder to a Git repository and create a Railway project from it.
2. Add a Railway PostgreSQL database service and connect it to this app so `DATABASE_URL` is injected.
3. Set the variables shown in `.env.example`, especially a strong `SECRET_KEY`, `CSRF_TRUSTED_ORIGINS`, `INITIAL_CHILD_PASSWORD`, and `INITIAL_GUARDIAN_PASSWORD`.
4. Deploy. The container migrates the database, seeds the six accounts and starter store entries, then starts Gunicorn.
5. Provide per-account password variables instead of the shared initial variables before the first account creation when each family member should begin with a different password. A future account-settings screen can support self-service password changes.

The initial usernames are `kj`, `astoria`, `saphira`, `dad`, `mom`, and `gg`.

## iPhone Installation

Open the Railway HTTPS URL in Safari, tap the Share button, then choose **Add to Home Screen**. Each device signs into the relevant account and reads the same online family data.
