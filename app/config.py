import os
from dataclasses import dataclass
from functools import lru_cache

OTP_DIGITS = 6
_DEV_SECRET = "dev-only-insecure-secret-change-me"


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    jwt_secret: str
    jwt_algorithm: str
    jwt_expire_minutes: int
    otp_ttl_seconds: int
    otp_max_attempts: int
    max_resume_bytes: int
    debug_return_otp: bool
    cors_origins: list
    totp_issuer: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    whatsapp_token: str
    whatsapp_phone_number_id: str
    whatsapp_template_name: str

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    settings = Settings(
        app_env=os.getenv("APP_ENV", "development").lower(),
        database_url=os.getenv(
            "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/onboarding"
        ),
        jwt_secret=os.getenv("JWT_SECRET", _DEV_SECRET),
        jwt_algorithm="HS256",
        jwt_expire_minutes=int(os.getenv("JWT_EXPIRE_MINUTES", "60")),
        otp_ttl_seconds=int(os.getenv("OTP_TTL_SECONDS", "300")),
        otp_max_attempts=int(os.getenv("OTP_MAX_ATTEMPTS", "5")),
        max_resume_bytes=int(os.getenv("MAX_RESUME_BYTES", str(5 * 1024 * 1024))),
        debug_return_otp=_flag("DEBUG_RETURN_OTP", False),
        cors_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()],
        totp_issuer=os.getenv("TOTP_ISSUER", "EdTech Onboarding"),
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_from=os.getenv("SMTP_FROM", "no-reply@example.com"),
        whatsapp_token=os.getenv("WHATSAPP_TOKEN", ""),
        whatsapp_phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""),
        whatsapp_template_name=os.getenv("WHATSAPP_TEMPLATE_NAME", "otp_verification"),
    )
    if settings.is_production:
        if settings.jwt_secret == _DEV_SECRET or len(settings.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be set to a random value of 32+ characters in production")
        if settings.debug_return_otp:
            raise RuntimeError("DEBUG_RETURN_OTP must be false in production")
    return settings
