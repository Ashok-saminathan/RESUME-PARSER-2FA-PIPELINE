from fastapi import APIRouter, Depends

from app.models import User
from app.routers.deps import get_current_user
from app.schemas.profile import DashboardRoute

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _profile_complete(user: User) -> bool:
    return bool(user.full_name and user.phone and user.qualification and user.skills)


@router.get("/route", response_model=DashboardRoute)
async def dashboard_route(user: User = Depends(get_current_user)):
    """Final routing payload: tells the frontend where to send the verified user."""
    return DashboardRoute(
        user_id=user.id,
        role=user.role,
        state="active",
        profile_complete=_profile_complete(user),
        redirect_url="/dashboard/student",
    )
