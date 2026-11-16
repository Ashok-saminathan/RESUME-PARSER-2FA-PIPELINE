"""Password hashing (Argon2id), OTP hashing, RFC 6238 TOTP and JWT helpers."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional
from urllib.parse import quote

import jwt

from app.config import OTP_DIGITS, get_settings

# --------------------------------------------------------------------------- passwords


@lru_cache
def _hasher():
    from argon2 import PasswordHasher  # argon2-cffi defaults to Argon2id

    return PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    from argon2.exceptions import InvalidHashError, VerificationError

    try:
        return _hasher().verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# --------------------------------------------------------------------------- OTP (email / WhatsApp)


def generate_numeric_otp(digits: int = OTP_DIGITS) -> str:
    return str(secrets.randbelow(10 ** digits)).zfill(digits)


def hash_otp(challenge_id, code: str) -> str:
    """Keyed hash bound to the challenge id, so a leaked hash cannot be replayed elsewhere."""
    key = get_settings().jwt_secret.encode()
    return hmac.new(key, f"{challenge_id}:{code}".encode(), hashlib.sha256).hexdigest()


def verify_otp_hash(challenge_id, code: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(challenge_id, code), expected_hash)


# --------------------------------------------------------------------------- TOTP (RFC 6238)


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    return base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)


def _hotp(key: bytes, counter: int, digits: int) -> str:
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    value = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(value).zfill(digits)


def totp_at(secret: str, at: Optional[float] = None, step: int = 30, digits: int = OTP_DIGITS) -> str:
    at = time.time() if at is None else at
    return _hotp(_key(secret), int(at // step), digits)


def verify_totp(
    secret: str, code: str, at: Optional[float] = None,
    step: int = 30, digits: int = OTP_DIGITS, window: int = 1,
) -> bool:
    if len(code) != digits or not code.isdigit():
        return False
    at = time.time() if at is None else at
    counter, key, ok = int(at // step), _key(secret), False
    for offset in range(-window, window + 1):  # no early exit, keeps timing uniform
        if hmac.compare_digest(_hotp(key, counter + offset, digits), code):
            ok = True
    return ok


def totp_uri(secret: str, account: str, issuer: str) -> str:
    return (
        f"otpauth://totp/{quote(issuer)}:{quote(account)}"
        f"?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits={OTP_DIGITS}&period=30"
    )


# --------------------------------------------------------------------------- JWT


def create_access_token(subject: str, role: str) -> tuple:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires = timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + expires,
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expires.total_seconds())


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError on any invalid, tampered or expired token."""
    settings = get_settings()
    return jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub"]},
    )
