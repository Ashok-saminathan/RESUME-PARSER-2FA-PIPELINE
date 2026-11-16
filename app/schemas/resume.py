import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ExperienceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Optional[str] = Field(default=None, max_length=150)
    company: Optional[str] = Field(default=None, max_length=150)
    duration: Optional[str] = Field(default=None, max_length=60)
    description: Optional[str] = Field(default=None, max_length=1000)


class ParsedResume(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    qualification: Optional[str] = None
    skills: list = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    total_experience_years: Optional[float] = None


class ResumeParseResponse(BaseModel):
    resume_id: uuid.UUID
    filename: str
    parsed: ParsedResume
