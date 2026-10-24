"""Load SYNTHETIC demo patients and recordings:  python -m app.demo_data"""
import random
from datetime import date, timedelta

from sqlalchemy import func, select

from .db import Base, SessionLocal, engine
from .models import Patient, Recording

NAMES = ["Asha Rao", "Ravi Kumar", "Meera Iyer", "Kiran Patel", "Sneha Reddy", "Vikram Singh", "Anita Das", "Arjun Nair"]
INDICATIONS = ["Palpitations", "Syncope evaluation", "Post-MI follow-up", "Dizziness", "Suspected arrhythmia"]


def main():
    Base.metadata.create_all(bind=engine)
    rng = random.Random(7)
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(Patient)):
            print("Patients already exist; skipping demo data")
            return
        for i, name in enumerate(NAMES, start=1):
            p = Patient(full_name=name, age=rng.randint(28, 82), sex=rng.choice("MF"),
                        phone=f"90000{i:05d}", indication=rng.choice(INDICATIONS), notes="Synthetic demo record")
            db.add(p)
            db.flush()
            p.mrn = f"HP-{p.id:05d}"
            for k in range(rng.randint(1, 3)):
                avg = rng.randint(62, 92)
                af = rng.random() < 0.2
                db.add(Recording(
                    patient_id=p.id, recorded_on=date.today() - timedelta(days=rng.randint(1, 120)),
                    duration_hours=rng.choice([24, 24, 48]), avg_hr=avg, min_hr=avg - rng.randint(15, 25),
                    max_hr=avg + rng.randint(35, 70), pvc_count=rng.randint(0, 900), pause_count=rng.randint(0, 3),
                    af_detected=af, status=rng.choice(["pending", "reviewed"]),
                    summary="Synthetic demo data. Not a clinical report.",
                ))
        db.commit()
    print("Demo data loaded")


if __name__ == "__main__":
    main()
