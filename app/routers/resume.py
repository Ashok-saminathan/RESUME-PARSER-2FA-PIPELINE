import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import UserResume
from app.schemas.resume import ResumeParseResponse
from app.services.resume_parser import ResumeParseError, parse_resume_bytes

router = APIRouter(prefix="/resume", tags=["resume"])

ALLOWED_EXTENSIONS = {".pdf", ".docx"}


@router.post("/parse", response_model=ResumeParseResponse)
async def parse_resume(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    filename = Path(file.filename or "").name[:255]
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only .pdf and .docx files are accepted")

    data = await file.read(settings.max_resume_bytes + 1)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty")
    if len(data) > settings.max_resume_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File is larger than {settings.max_resume_bytes // (1024 * 1024)} MB",
        )

    try:
        parsed = await run_in_threadpool(parse_resume_bytes, data, ext)  # parsing is blocking work
    except ResumeParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    row = UserResume(
        filename=filename,
        content_type=file.content_type,
        file_size=len(data),
        file_sha256=hashlib.sha256(data).hexdigest(),
        parsed_data=parsed.model_dump(mode="json"),
    )
    db.add(row)
    await db.commit()
    return ResumeParseResponse(resume_id=row.id, filename=filename, parsed=parsed)
