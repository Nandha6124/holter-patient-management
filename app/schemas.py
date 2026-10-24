from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, model_validator


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PatientIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    age: int = Field(ge=0, le=120)
    sex: Literal["M", "F", "O"]
    phone: str = Field(default="", max_length=30)
    indication: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2000)


class PatientOut(PatientIn):
    id: int
    mrn: str
    created_at: datetime
    recording_count: int = 0


class RecordingIn(BaseModel):
    recorded_on: date
    duration_hours: float = Field(gt=0, le=240)
    avg_hr: int = Field(ge=20, le=250)
    min_hr: int = Field(ge=20, le=250)
    max_hr: int = Field(ge=20, le=250)
    pvc_count: int = Field(default=0, ge=0, le=1_000_000)
    pause_count: int = Field(default=0, ge=0, le=100_000)
    af_detected: bool = False
    summary: str = Field(default="", max_length=3000)
    status: Literal["pending", "reviewed"] = "pending"

    @model_validator(mode="after")
    def hr_in_order(self):
        if not (self.min_hr <= self.avg_hr <= self.max_hr):
            raise ValueError("Heart rates must satisfy min <= average <= max")
        return self


class RecordingOut(RecordingIn):
    id: int
    patient_id: int


class RecentRecording(RecordingOut):
    patient_name: str
    patient_mrn: str


class Summary(BaseModel):
    total_patients: int
    total_recordings: int
    pending_review: int
    af_flagged: int
    avg_heart_rate: Optional[float]
    recent: List[RecentRecording]
