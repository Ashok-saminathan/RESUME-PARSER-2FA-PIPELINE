import time
import uuid

import jwt
import pytest

from app.services import security

# RFC 6238 Appendix B test vectors (SHA-1), secret = ASCII "12345678901234567890"
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


@pytest.mark.parametrize("at,expected", [(59, "94287082"), (1111111109, "07081804"), (1234567890, "89005924")])
def test_totp_matches_rfc6238_vectors(at, expected):
    assert security.totp_at(RFC_SECRET, at=at, digits=8) == expected


def test_totp_verify_window():
    secret = security.generate_totp_secret()
    now = 1_700_000_000
    code = security.totp_at(secret, at=now)
    assert security.verify_totp(secret, code, at=now)
    assert security.verify_totp(secret, code, at=now + 30)       # one step later is allowed
    assert not security.verify_totp(secret, code, at=now + 120)  # outside the window
    assert not security.verify_totp(secret, "abcdef", at=now)
    assert not security.verify_totp(secret, "12345", at=now)


def test_totp_uri_contains_secret_and_issuer():
    uri = security.totp_uri("ABCDEF", "a@b.com", "My App")
    assert uri.startswith("otpauth://totp/My%20App:a%40b.com?secret=ABCDEF")


def test_otp_generation_and_hash_binding():
    code = security.generate_numeric_otp()
    assert len(code) == 6 and code.isdigit()
    cid = uuid.uuid4()
    digest = security.hash_otp(cid, code)
    assert security.verify_otp_hash(cid, code, digest)
    assert not security.verify_otp_hash(cid, "000000" if code != "000000" else "111111", digest)
    assert not security.verify_otp_hash(uuid.uuid4(), code, digest)  # bound to the challenge id


def test_jwt_roundtrip_and_tamper():
    token, expires_in = security.create_access_token("user-1", "student")
    assert expires_in == 3600
    payload = security.decode_access_token(token)
    assert payload["sub"] == "user-1" and payload["role"] == "student"
    with pytest.raises(jwt.PyJWTError):
        security.decode_access_token(token[:-2] + ("AA" if not token.endswith("AA") else "BB"))


def test_jwt_expired_and_wrong_secret():
    settings = security.get_settings()
    expired = jwt.encode({"sub": "x", "exp": int(time.time()) - 10}, settings.jwt_secret, algorithm="HS256")
    with pytest.raises(jwt.ExpiredSignatureError):
        security.decode_access_token(expired)
    forged = jwt.encode({"sub": "x", "exp": int(time.time()) + 100}, "another-secret-another-secret-12", algorithm="HS256")
    with pytest.raises(jwt.PyJWTError):
        security.decode_access_token(forged)


def test_argon2id_hash_and_verify():
    pytest.importorskip("argon2")
    hashed = security.hash_password("Str0ngPassw0rd!")
    assert hashed.startswith("$argon2id$")
    assert security.verify_password("Str0ngPassw0rd!", hashed)
    assert not security.verify_password("wrong-password1", hashed)
