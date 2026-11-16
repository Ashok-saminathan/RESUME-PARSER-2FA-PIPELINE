import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import clean_skills, normalize_phone
from app.schemas.resume import ExperienceItem, ParsedResume


class ResumeSummary(BaseModel):
    resume_id: uuid.UUID
    filename: str
    parsed: ParsedResume


class ProfileResponse(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    phone: Optional[str] = None
    qualification: Optional[str] = None
    skills: list = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    is_email_verified: bool
    resume: Optional[ResumeSummary] = None


class ProfileUpdate(BaseModel):
    """Partial update. Email is intentionally not editable (changing it needs re-verification)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    phone: Optional[str] = None
    qualification: Optional[str] = Field(default=None, max_length=200)
    skills: Optional[list] = Field(default=None, max_length=50)
    experience: Optional[list[ExperienceItem]] = Field(default=None, max_length=30)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v) if v else None

    @field_validator("skills")
    @classmethod
    def _skills(cls, v: Optional[list]) -> Optional[list]:
        return clean_skills(v) if v is not None else None

    @model_validator(mode="after")
    def _required_fields_not_null(self):
        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError("full_name cannot be null")
        if "skills" in self.model_fields_set and self.skills is None:
            raise ValueError("skills cannot be null")
        if "experience" in self.model_fields_set and self.experience is None:
            raise ValueError("experience cannot be null")
        return self


class DashboardRoute(BaseModel):
    user_id: uuid.UUID
    role: str
    state: str
    profile_complete: bool
    redirect_url: str
