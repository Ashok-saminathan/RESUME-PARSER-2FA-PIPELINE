from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UserResume
from app.routers.deps import get_current_user
from app.schemas.profile import ProfileResponse, ProfileUpdate, ResumeSummary
from app.schemas.resume import ParsedResume

router = APIRouter(prefix="/profile", tags=["profile"])


async def _build_profile(db: AsyncSession, user: User) -> ProfileResponse:
    resume = await db.scalar(
        select(UserResume)
        .where(UserResume.user_id == user.id)
        .order_by(UserResume.created_at.desc())
        .limit(1)
    )
    summary = None
    if resume is not None:
        summary = ResumeSummary(
            resume_id=resume.id,
            filename=resume.filename,
            parsed=ParsedResume.model_validate(resume.parsed_data),
        )
    return ProfileResponse(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        qualification=user.qualification,
        skills=user.skills or [],
        experience=user.experience or [],
        is_email_verified=user.is_email_verified,
        resume=summary,
    )


@router.get("", response_model=ProfileResponse)
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _build_profile(db, user)


@router.patch("", response_model=ProfileResponse)
async def update_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(user, key, value)
    if changes:
        db.add(user)
        await db.commit()
    return await _build_profile(db, user)
