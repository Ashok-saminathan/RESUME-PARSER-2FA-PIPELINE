"""2FA challenge creation, dispatch and verification."""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import OTPChallenge, User
from app.schemas.auth import Channel
from app.services import notification
from app.services.security import (
    generate_numeric_otp,
    generate_totp_secret,
    hash_otp,
    totp_uri,
    verify_otp_hash,
    verify_totp,
)


@dataclass
class IssuedChallenge:
    challenge: OTPChallenge
    otp: Optional[str] = None          # email / whatsapp only, never persisted in clear
    totp_secret: Optional[str] = None  # browser only
    totp_uri: Optional[str] = None


async def create_challenge(db: AsyncSession, user: User, channel: Channel) -> IssuedChallenge:
    settings = get_settings()
    now = datetime.now(timezone.utc)

    # Only the newest challenge may be used: invalidate any earlier open ones.
    await db.execute(
        update(OTPChallenge)
        .where(OTPChallenge.user_id == user.id, OTPChallenge.consumed_at.is_(None))
        .values(consumed_at=now)
    )

    challenge = OTPChallenge(
        id=uuid.uuid4(),
        user_id=user.id,
        channel=channel.value,
        attempts=0,
        max_attempts=settings.otp_max_attempts,
        expires_at=now + timedelta(seconds=settings.otp_ttl_seconds),
    )
    issued = IssuedChallenge(challenge=challenge)

    if channel == Channel.browser:
        secret = generate_totp_secret()
        challenge.totp_secret = secret
        issued.totp_secret = secret
        issued.totp_uri = totp_uri(secret, user.email, settings.totp_issuer)
    else:
        code = generate_numeric_otp()
        challenge.code_hash = hash_otp(challenge.id, code)
        issued.otp = code

    db.add(challenge)
    await db.flush()
    return issued


async def dispatch_challenge(user: User, issued: IssuedChallenge) -> None:
    """Send the OTP. Browser TOTP has nothing to send: the authenticator generates the code."""
    settings = get_settings()
    channel = issued.challenge.channel
    try:
        if channel == Channel.email.value:
            await notification.send_email_otp(user.email, issued.otp, settings.otp_ttl_seconds)
        elif channel == Channel.whatsapp.value:
            await notification.send_whatsapp_otp(user.phone, issued.otp)
    except notification.DeliveryError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not deliver the verification code") from exc


async def verify_challenge(db: AsyncSession, challenge_id: uuid.UUID, code: str) -> User:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(OTPChallenge).where(OTPChallenge.id == challenge_id).with_for_update()
    )
    challenge = result.scalar_one_or_none()

    if challenge is None or challenge.consumed_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or already used verification challenge")
    if challenge.expires_at <= now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Verification code has expired")
    if challenge.attempts >= challenge.max_attempts:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Request a new code.")

    if challenge.channel == Channel.browser.value:
        valid = verify_totp(challenge.totp_secret, code)
    else:
        valid = verify_otp_hash(challenge.id, code, challenge.code_hash)

    if not valid:
        challenge.attempts += 1
        await db.commit()  # persist the failed attempt before responding
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect verification code")

    challenge.consumed_at = now
    user = await db.get(User, challenge.user_id)
    user.is_active = True
    if challenge.channel == Channel.email.value:
        user.is_email_verified = True  # only the email channel proves ownership of the address
    await db.commit()
    return user
