# Smart Holter Monitoring & Patient Management System

A web app for clinic staff to register patients, log Holter (24-48 hour ECG) monitoring results, and review them on a dashboard.

> **Demonstration software for learning. Use synthetic data only. It is not a medical device and must not be used for clinical decisions.**

**Stack:** HTML, CSS, vanilla JavaScript (ES modules, no build step), Python, FastAPI, SQLAlchemy, SQLite, JWT + bcrypt

## Features
- **Secure staff login**: bcrypt-hashed passwords, JWT sessions; every `/api` data route requires a valid token
- **Patient registration**: auto-generated MRN (`HP-00001`), demographics, indication, notes
- **Add / update / delete / search** for patients (name, MRN or phone) and for their Holter recordings
- **Recording details**: duration, average / min / max heart rate, PVC count, pauses, AF flag, findings, review status
- **Dashboard**: patient and recording totals, pending reviews, AF-flagged recordings, mean heart rate, recent recordings
- **Validation** on both sides (e.g. min <= average <= max heart rate, realistic ranges)
- **Responsive UI** that works on phones; patient data is rendered with `textContent` so it cannot inject markup (XSS-safe)

## Run
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set SECRET_KEY, ADMIN_EMAIL and ADMIN_PASSWORD
python -m app.demo_data         # optional: load synthetic demo patients
uvicorn app.main:app --reload
```
Open http://localhost:8000 and sign in with the admin email and password from `.env`. The first staff account is created automatically on startup when no users exist. Add more with:
```bash
python -m app.create_user nurse@example.com 'a-strong-password'
```

## Tests
```bash
pytest
```
Covers authentication, route protection, expired tokens, patient and recording CRUD, search (including wildcard escaping), validation, cascade deletes, the dashboard and static file serving.

## Docker
```bash
docker build -t holter-pms .
docker run -p 8000:8000 -v holter-data:/data --env-file .env holter-pms
```

## Limitations
No audit log, role-based permissions, ECG waveform import or login rate limiting. A real clinical system would need these, plus regulatory compliance.
