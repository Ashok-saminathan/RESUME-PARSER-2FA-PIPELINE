import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import clean_skills, normalize_email, normalize_phone
from app.schemas.resume import ExperienceItem


class Channel(str, Enum):
    email = "email"
    whatsapp = "whatsapp"
    browser = "browser"


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=2, max_length=120)
    email: str
    phone: Optional[str] = None
    password: str = Field(min_length=8, max_length=128)
    qualification: Optional[str] = Field(default=None, max_length=200)
    skills: list = Field(default_factory=list, max_length=50)
    experience: list[ExperienceItem] = Field(default_factory=list, max_length=30)
    resume_id: Optional[uuid.UUID] = None
    channel: Channel = Channel.email

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v) if v else None

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must contain at least one letter and one digit")
        return v

    @field_validator("skills")
    @classmethod
    def _skills(cls, v: list) -> list:
        return clean_skills(v)

    @model_validator(mode="after")
    def _channel_needs_destination(self):
        if self.channel == Channel.whatsapp and not self.phone:
            raise ValueError("A phone number is required for WhatsApp verification")
        return self


class RegisterResponse(BaseModel):
    user_id: uuid.UUID
    challenge_id: uuid.UUID
    channel: Channel
    expires_at: datetime
    message: str
    totp_secret: Optional[str] = None
    totp_uri: Optional[str] = None
    dev_otp: Optional[str] = None


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    challenge_id: uuid.UUID
    code: str = Field(pattern=r"^\d{6}$")


class UserBrief(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserBrief
    next_step: str = "profile_preview"
    redirect_url: str = "/profile/preview"
