from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import schemas
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .models import Patient, Recording, User
from .security import create_token, current_user, hash_password, verify_password

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Holter Patient Management System")
api = APIRouter(prefix="/api")
protected = APIRouter(prefix="/api", dependencies=[Depends(current_user)])  # every route here needs a valid JWT


def bootstrap_admin():
    """Create the first staff account from env vars when the users table is empty."""
    if not (settings.admin_email and settings.admin_password):
        return
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User)) == 0:
            db.add(User(email=settings.admin_email.lower(), password_hash=hash_password(settings.admin_password)))
            db.commit()


bootstrap_admin()


# ---------- auth ----------
@api.post("/auth/login", response_model=schemas.TokenOut)
def login(body: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return schemas.TokenOut(access_token=create_token(user.id))


@protected.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email}


# ---------- patients ----------
def _patient_out(db: Session, p: Patient) -> schemas.PatientOut:
    count = db.scalar(select(func.count()).select_from(Recording).where(Recording.patient_id == p.id))
    return schemas.PatientOut(
        id=p.id, mrn=p.mrn, full_name=p.full_name, age=p.age, sex=p.sex, phone=p.phone,
        indication=p.indication, notes=p.notes, created_at=p.created_at, recording_count=count or 0,
    )


def _get_patient(db: Session, patient_id: int) -> Patient:
    p = db.get(Patient, patient_id)
    if p is None:
        raise HTTPException(404, "Patient not found")
    return p


@protected.get("/patients", response_model=List[schemas.PatientOut])
def list_patients(
    q: Optional[str] = Query(None, max_length=100),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Patient).order_by(Patient.id.desc())
    if q and q.strip():
        term = q.strip()
        stmt = stmt.where(
            or_(
                Patient.full_name.icontains(term, autoescape=True),
                Patient.mrn.icontains(term, autoescape=True),
                Patient.phone.icontains(term, autoescape=True),
            )
        )
    return [_patient_out(db, p) for p in db.scalars(stmt.limit(limit).offset(offset))]


@protected.post("/patients", response_model=schemas.PatientOut, status_code=201)
def create_patient(body: schemas.PatientIn, db: Session = Depends(get_db)):
    p = Patient(**body.model_dump())
    db.add(p)
    db.flush()
    p.mrn = f"HP-{p.id:05d}"
    db.commit()
    return _patient_out(db, p)


@protected.get("/patients/{patient_id}", response_model=schemas.PatientOut)
def get_patient(patient_id: int, db: Session = Depends(get_db)):
    return _patient_out(db, _get_patient(db, patient_id))


@protected.put("/patients/{patient_id}", response_model=schemas.PatientOut)
def update_patient(patient_id: int, body: schemas.PatientIn, db: Session = Depends(get_db)):
    p = _get_patient(db, patient_id)
    for field, value in body.model_dump().items():
        setattr(p, field, value)
    db.commit()
    return _patient_out(db, p)


@protected.delete("/patients/{patient_id}", status_code=204)
def delete_patient(patient_id: int, db: Session = Depends(get_db)):
    db.delete(_get_patient(db, patient_id))
    db.commit()


# ---------- recordings ----------
@protected.get("/patients/{patient_id}/recordings", response_model=List[schemas.RecordingOut])
def list_recordings(patient_id: int, db: Session = Depends(get_db)):
    return [schemas.RecordingOut.model_validate(r, from_attributes=True) for r in _get_patient(db, patient_id).recordings]


@protected.post("/patients/{patient_id}/recordings", response_model=schemas.RecordingOut, status_code=201)
def add_recording(patient_id: int, body: schemas.RecordingIn, db: Session = Depends(get_db)):
    _get_patient(db, patient_id)
    rec = Recording(patient_id=patient_id, **body.model_dump())
    db.add(rec)
    db.commit()
    return schemas.RecordingOut.model_validate(rec, from_attributes=True)


def _get_recording(db: Session, rec_id: int) -> Recording:
    rec = db.get(Recording, rec_id)
    if rec is None:
        raise HTTPException(404, "Recording not found")
    return rec


@protected.put("/recordings/{rec_id}", response_model=schemas.RecordingOut)
def update_recording(rec_id: int, body: schemas.RecordingIn, db: Session = Depends(get_db)):
    rec = _get_recording(db, rec_id)
    for field, value in body.model_dump().items():
        setattr(rec, field, value)
    db.commit()
    return schemas.RecordingOut.model_validate(rec, from_attributes=True)


@protected.delete("/recordings/{rec_id}", status_code=204)
def delete_recording(rec_id: int, db: Session = Depends(get_db)):
    db.delete(_get_recording(db, rec_id))
    db.commit()


# ---------- dashboard ----------
@protected.get("/dashboard", response_model=schemas.Summary)
def dashboard(db: Session = Depends(get_db)):
    count = lambda stmt: db.scalar(stmt) or 0  # noqa: E731
    recent_rows = db.execute(
        select(Recording, Patient).join(Patient).order_by(Recording.recorded_on.desc(), Recording.id.desc()).limit(6)
    ).all()
    avg = db.scalar(select(func.avg(Recording.avg_hr)))
    return schemas.Summary(
        total_patients=count(select(func.count()).select_from(Patient)),
        total_recordings=count(select(func.count()).select_from(Recording)),
        pending_review=count(select(func.count()).select_from(Recording).where(Recording.status == "pending")),
        af_flagged=count(select(func.count()).select_from(Recording).where(Recording.af_detected.is_(True))),
        avg_heart_rate=round(avg, 1) if avg is not None else None,
        recent=[
            schemas.RecentRecording(
                **schemas.RecordingOut.model_validate(r, from_attributes=True).model_dump(),
                patient_name=p.full_name, patient_mrn=p.mrn,
            )
            for r, p in recent_rows
        ],
    )


app.include_router(api)
app.include_router(protected)

# Serve the HTML/CSS/JS frontend (mounted last so /api routes win)
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static", html=True), name="static")
