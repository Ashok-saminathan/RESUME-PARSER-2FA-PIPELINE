import pytest
from pydantic import ValidationError

from app.schemas.auth import Channel, RegisterRequest, VerifyRequest
from app.schemas.profile import ProfileUpdate

BASE = {"full_name": "Arun Kumar", "email": "Arun@Example.com", "password": "Str0ngPassw0rd!"}


def test_register_normalizes_email_phone_skills():
    req = RegisterRequest(**BASE, phone="98765 43210", skills=["Python", " python ", "SQL", ""])
    assert req.email == "arun@example.com"
    assert req.phone == "+919876543210"
    assert req.skills == ["Python", "SQL"]
    assert req.channel == Channel.email


@pytest.mark.parametrize("bad", [
    {"password": "short1"}, {"password": "onlyletters"}, {"password": "12345678"},
    {"email": "not-an-email"}, {"phone": "12345"}, {"unknown_field": 1},
])
def test_register_rejects_bad_input(bad):
    with pytest.raises(ValidationError):
        RegisterRequest(**{**BASE, **bad})


def test_whatsapp_channel_requires_phone():
    with pytest.raises(ValidationError):
        RegisterRequest(**BASE, channel="whatsapp")
    assert RegisterRequest(**BASE, phone="+919876543210", channel="whatsapp").channel == Channel.whatsapp


def test_verify_code_must_be_six_digits():
    cid = "7f0a1d5c-3b0e-4f43-8c63-0f8a9e0b1c2d"
    assert VerifyRequest(challenge_id=cid, code="123456")
    for bad in ("12345", "1234567", "abcdef", "12 456"):
        with pytest.raises(ValidationError):
            VerifyRequest(challenge_id=cid, code=bad)


def test_profile_update_is_partial_and_rejects_nulls_and_email():
    update = ProfileUpdate(skills=["Go", "go", "Rust"])
    assert update.model_dump(exclude_unset=True) == {"skills": ["Go", "Rust"]}
    for bad in ({"full_name": None}, {"skills": None}, {"email": "x@y.com"}):
        with pytest.raises(ValidationError):
            ProfileUpdate(**bad)
