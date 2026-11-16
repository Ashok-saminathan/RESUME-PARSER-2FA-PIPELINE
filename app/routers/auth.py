from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import User, UserResume
from app.schemas.auth import (
    Channel,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserBrief,
    VerifyRequest,
)
from app.services.notification import mask_email, mask_phone
from app.services.otp_service import create_challenge, dispatch_challenge, verify_challenge
from app.services.security import create_access_token, hash_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    settings = get_settings()

    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing is not None and existing.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    # Argon2id is deliberately slow and CPU-bound: keep it off the event loop.
    password_hash = await run_in_threadpool(hash_password, payload.password)

    fields = dict(
        full_name=payload.full_name,
        phone=payload.phone,
        password_hash=password_hash,
        qualification=payload.qualification,
        skills=payload.skills,
        experience=[item.model_dump() for item in payload.experience],
    )
    if existing is not None:  # an unverified earlier attempt: let the person retry
        user = existing
        for key, value in fields.items():
            setattr(user, key, value)
    else:
        user = User(email=payload.email, is_active=False, **fields)
        db.add(user)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    if payload.resume_id is not None:
        resume = await db.get(UserResume, payload.resume_id)
        if resume is None or resume.user_id not in (None, user.id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Resume not found or already used")
        resume.user_id = user.id

    issued = await create_challenge(db, user, payload.channel)
    await db.commit()
    await dispatch_challenge(user, issued)  # after commit, so the challenge exists before the code arrives

    messages = {
        Channel.email: f"Verification code sent to {mask_email(user.email)}",
        Channel.whatsapp: f"Verification code sent on WhatsApp to {mask_phone(user.phone or '')}",
        Channel.browser: "Add the secret to your authenticator app, then enter the 6-digit code",
    }
    return RegisterResponse(
        user_id=user.id,
        challenge_id=issued.challenge.id,
        channel=payload.channel,
        expires_at=issued.challenge.expires_at,
        message=messages[payload.channel],
        totp_secret=issued.totp_secret,
        totp_uri=issued.totp_uri,
        dev_otp=issued.otp if settings.debug_return_otp else None,
    )


@router.post("/verify-2fa", response_model=TokenResponse)
async def verify_2fa(payload: VerifyRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await verify_challenge(db, payload.challenge_id, payload.code)
    token, expires_in = create_access_token(str(user.id), user.role)
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserBrief(user_id=user.id, full_name=user.full_name, email=user.email),
    )
