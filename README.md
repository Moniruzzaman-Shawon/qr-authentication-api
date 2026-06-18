# QR Authentication API

Django REST API for a one-time-use QR product authentication system. Each product
carries a **signed, single-use QR code**. A genuine product is **activated at point of
sale**; the first customer scan returns *genuine*, and any later scan returns
*suspicious* — surfacing counterfeits and duplicated codes. Suspicious scans trigger
email/SMS fraud alerts.

## Tech Stack

- Python 3.10+ · Django 5/6 · Django REST Framework
- JWT auth (`djangorestframework-simplejwt`)
- SQLite (dev) / PostgreSQL (prod)
- `qrcode` + Pillow (signed QR generation)
- Twilio (SMS) · SMTP (email)
- drf-spectacular (OpenAPI docs) · WhiteNoise · Gunicorn

## How the trust model works (two-phase activation)

Every product moves through a lifecycle, enforced by the verify endpoint:

| Status     | Meaning                                   | Customer scan result          |
|------------|-------------------------------------------|-------------------------------|
| `printed`  | Created at the factory, **not for sale**  | **Not activated** (alerted)   |
| `active`   | Activated at point of sale                | **Genuine** → `verified`      |
| `verified` | A customer has verified it once           | **Suspicious** → `flagged`    |
| `flagged`  | Scanned again after verification          | **Suspicious**                |

This defeats supply-chain pre-scanning: a code photographed before activation can
never verify as genuine. A database `UniqueConstraint` guarantees **at most one**
genuine scan per product, and verification runs inside a `select_for_update`
transaction, so concurrent scans can't both win.

QR payloads are **HMAC-signed** (`/verify/<uuid>?sig=...`); the API rejects missing or
tampered signatures, so leaked UUIDs can't be probed or forged.

## Roles

Two roles (Django Groups), checked on every endpoint:

- **Admin** — full control: products, deletes, user management, activation, dashboards.
- **Operator** — point-of-sale staff: activate codes and read dashboards. No deletes,
  no user management.

Public (no auth): only `verify` and `check`.

## Installation (local dev)

```bash
cd api
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then edit; for local dev set DEBUG=True
python manage.py migrate
python manage.py seed_admin   # creates the Admin user from INITIAL_ADMIN_* env vars
python manage.py runserver
```

API at `http://localhost:8000`. Interactive docs at `http://localhost:8000/api/docs/`.

> **Note:** `DEBUG` defaults to **False**. Local development requires a `.env` with
> `DEBUG=True` and a `SECRET_KEY` (see `.env.example`).

## API Endpoints

### Auth & users
| Method | URL | Role | Description |
|--------|-----|------|-------------|
| POST | `/api/auth/login/` | public | `{username, password}` → `{access, refresh, user}` |
| POST | `/api/auth/refresh/` | public | Rotate access token |
| POST | `/api/auth/logout/` | auth | Blacklist a refresh token |
| GET | `/api/auth/me/` | auth | Current user + role |
| GET/POST | `/api/users/` | Admin | List / create users |
| GET/PATCH/DELETE | `/api/users/<id>/` | Admin | Manage a user (DELETE = deactivate) |

### Products
| Method | URL | Role | Description |
|--------|-----|------|-------------|
| GET | `/api/products/` | Admin/Operator | List (paginated) |
| POST | `/api/products/` | Admin | Create (status `printed`) |
| GET | `/api/products/<uuid>/` | Admin/Operator | Detail + scan history |
| PUT/PATCH/DELETE | `/api/products/<uuid>/` | Admin | Update / delete |
| POST | `/api/products/bulk-create/` | Admin | Bulk create with batch numbers |
| POST | `/api/products/bulk-csv/` | Admin | Bulk create from CSV |
| POST | `/api/products/<uuid>/activate/` | Admin/Operator | Activate (printed → active) |
| POST | `/api/products/bulk-activate/` | Admin/Operator | Activate many `{ids:[...]}` |
| GET | `/api/products/download-qr/` | Admin/Operator | QR codes as ZIP (`?ids=`) |

### Verification (public)
| Method | URL | Description |
|--------|-----|-------------|
| POST | `/api/verify/<uuid>/?sig=` | Verify (records scan; genuine/suspicious/not_activated) |
| GET | `/api/check/<uuid>/?sig=` | Read status without recording a scan |

### Analytics & customers (Admin/Operator)
| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/scans/` | Scan records (paginated, `?is_first_scan=`) |
| GET | `/api/stats/` | Dashboard totals + status breakdown |
| GET | `/api/fraud-alerts/` | Suspicious scans (paginated) |
| GET | `/api/customers/` | Customers with aggregated scan data |
| GET | `/api/customers/<email>/` | Customer detail + scan history |

## Environment variables

All configuration is via environment / `.env` — see **`.env.example`** for the full,
commented list. Key ones:

- `DEBUG`, `SECRET_KEY` (required in prod), `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`
- `FRONTEND_URL` — embedded into every QR code (must be publicly reachable)
- `QR_SIGNING_KEY` — optional separate key for QR signatures
- `DB_*` / `DATABASE_URL` — Postgres (omit for SQLite)
- `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS`, `THROTTLE_*`
- `EMAIL_*`, `ALERT_RECIPIENT_EMAILS`, `TWILIO_*`, `ALERT_RECIPIENT_PHONES`
- `INITIAL_ADMIN_USERNAME/EMAIL/PASSWORD` — seeded by `manage.py seed_admin`

## Notifications

On a suspicious or not-activated scan, the brand is alerted by **email** (SMTP; console
in dev) and **SMS** (Twilio, if configured). Sending is fail-safe — a provider outage
never blocks verification. Set `NOTIFY_CUSTOMER_ON_GENUINE=True` to also email customers
a verification receipt.

## Tests

```bash
python manage.py test
```

Covers the verify flow (genuine / suspicious / not-activated), the one-genuine-scan
guarantee, signature rejection, activation + role enforcement, auth requirements, and
email masking.

## Deployment

The repo root ships a `docker-compose.yml` (Postgres + gunicorn API + nginx-served
client). From the repo root:

```bash
cp api/.env.example .env   # fill in real values; set DEBUG=False and a strong SECRET_KEY
docker compose up --build
```

App at `http://localhost:8080`. The API container runs migrations and `seed_admin` on
start. Generate a production secret key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

### Production checklist
- [ ] `DEBUG=False`, strong 50-char `SECRET_KEY`, real `ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS`
- [ ] `FRONTEND_URL` = the real public site (QR codes embed it)
- [ ] Postgres configured (`DB_*`), not SQLite
- [ ] TLS terminated in front of nginx; `SECURE_SSL_REDIRECT=True`
- [ ] SMTP + Twilio credentials and `ALERT_RECIPIENT_*` set
- [ ] `INITIAL_ADMIN_PASSWORD` set, then rotated after first login
- [ ] Media volume backed up / pointed at object storage (S3) for multi-instance
