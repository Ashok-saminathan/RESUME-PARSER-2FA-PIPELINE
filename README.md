# AI-Powered Resume Parser & Multi-Channel 2FA Onboarding Pipeline

FastAPI + async PostgreSQL. Flow: upload resume -> parse -> autofill form -> register (Argon2id) -> 2FA (Email / WhatsApp / Browser TOTP) -> JWT -> editable profile -> student dashboard.

## Layout

```
app/
  main.py              app factory, router wiring, /health
  config.py            env-based settings, production safety checks
  database.py          async engine + session dependency
  models/              User, UserResume, OTPChallenge (SQLAlchemy 2.0)
  schemas/             Pydantic v2 request/response models
  services/
    resume_parser.py   PDF/DOCX text extraction + field mapping
    security.py        Argon2id, OTP hashing, RFC 6238 TOTP, JWT
    otp_service.py     challenge create / dispatch / verify
    notification.py    SMTP email + WhatsApp Cloud API (console fallback in dev)
  routers/             resume, auth, profile, dashboard, deps (JWT guard)
migrations/001_init.sql
scripts/migrate.py     applies migrations once each; e2e.sh = cURL lifecycle test
tests/                 parser, security (TOTP vectors, JWT), schema validation
```

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit DATABASE_URL and JWT_SECRET, then: export $(grep -v '^#' .env | xargs)
python scripts/migrate.py     # creates users, user_resumes, otp_challenges
uvicorn app.main:app --reload
```

Docs UI: http://localhost:8000/docs

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/resume/parse` | none | multipart `file` (.pdf/.docx, 5 MB max) -> `resume_id` + parsed JSON |
| POST | `/api/v1/auth/register` | none | validate, Argon2id hash, stage inactive user, dispatch 2FA |
| POST | `/api/v1/auth/verify-2fa` | none | check code + expiry + attempts, activate user, issue JWT |
| GET | `/api/v1/profile` | Bearer | profile preview incl. parsed resume data |
| PATCH | `/api/v1/profile` | Bearer | partial update (name, phone, qualification, skills, experience) |
| GET | `/api/v1/dashboard/route` | Bearer | `{state, profile_complete, redirect_url: "/dashboard/student"}` |

`register` takes `channel`: `email` (default), `whatsapp` (needs `phone`) or `browser`.
For `browser`, the response contains `totp_secret` and `totp_uri` (render as a QR code); the user enters the 6-digit code from their authenticator app.

## Testing

```bash
pytest                                   # unit tests: parser, TOTP/JWT, schemas
DEBUG_RETURN_OTP=true uvicorn app.main:app   # in one terminal
bash scripts/e2e.sh                      # full lifecycle with cURL, incl. negative cases
```

`DEBUG_RETURN_OTP=true` returns the OTP in the register response so the lifecycle can be scripted. The app refuses to start in production with it enabled.

## Design notes and limits

- **Parser is heuristic.** Regex + section detection. Works on conventional single-column resumes; scanned (image-only) PDFs are rejected, text boxes in DOCX are not read. The user edits the autofilled form before submitting.
- **Argon2id** is used through `argon2-cffi` directly (what Passlib wraps).
- **OTPs** are stored as HMAC-SHA256 hashes bound to the challenge id, expire after 5 minutes, allow 5 attempts, are single-use, and a new challenge invalidates older ones. The attempt counter is updated under a row lock.
- **Email ownership:** only the email channel sets `is_email_verified`. WhatsApp/TOTP prove control of a phone/device, not of the email address.
- **TOTP secret** is stored in plaintext in `otp_challenges`; encrypt it at rest (e.g. KMS/Fernet) before real use.
- **WhatsApp** needs an approved Meta authentication template named by `WHATSAPP_TEMPLATE_NAME`.
- **Not included:** rate limiting on `/resume/parse` and `/register` (add e.g. a reverse-proxy limit or slowapi), a login endpoint for returning users, cleanup of unclaimed `user_resumes` rows, refresh tokens.
