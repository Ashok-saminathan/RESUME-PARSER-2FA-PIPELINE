from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, dashboard, profile, resume


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()  # fail fast on unsafe production configuration
    yield


app = FastAPI(title="Resume Parser & 2FA Onboarding", version="1.0.0", lifespan=lifespan)

settings = get_settings()
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )

for module in (resume, auth, profile, dashboard):
    app.include_router(module.router, prefix="/api/v1")


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}
