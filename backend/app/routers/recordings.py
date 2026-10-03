import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import storage
from ..config import settings
from ..db import get_db
from ..events import set_status
from ..models import JobEvent, Recording, Status
from ..schemas import (
    ALLOWED_EXTENSIONS,
    ALLOWED_LANGUAGES,
    PresignRequest,
    PresignResponse,
    RecordingDetail,
    RecordingListItem,
)

router = APIRouter(prefix="/api/recordings", tags=["recordings"])


def session_id(x_session_id: str | None = Header(default=None)) -> str:
    """Retrieve or default the anonymous per-browser session identifier."""
    return x_session_id or "anonymous"


@router.post("/presign", response_model=PresignResponse)
def presign(
    req: PresignRequest,
    db: Session = Depends(get_db),
    sid: str = Depends(session_id),
):
    """Validate upload parameters, create database record, and return a signed upload URL."""
    ext = req.filename.rsplit(".", 1)[-1].lower() if "." in req.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '.{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    if req.size_bytes > settings.MAX_UPLOAD_BYTES:
        mb = settings.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise HTTPException(400, f"File exceeds the {mb} MB size limit.")
    if req.language_code not in ALLOWED_LANGUAGES:
        raise HTTPException(400, f"Unsupported language '{req.language_code}'.")

    rec_id = uuid.uuid4()
    key = f"{sid}/{rec_id}/original.{ext}"
    rec = Recording(
        id=rec_id,
        filename=req.filename,
        content_type=req.content_type,
        size_bytes=req.size_bytes,
        language_code=req.language_code,
        storage_key=key,
        status=Status.UPLOADING,
        owner_session=sid,
    )
    db.add(rec)
    db.add(JobEvent(recording_id=rec_id, to_status=Status.UPLOADING))

    try:
        upload_url = storage.create_signed_upload_url(key)
    except storage.StorageError as e:
        raise HTTPException(502, f"Could not prepare upload URL: {e}")

    db.commit()
    return PresignResponse(
        recording_id=rec_id, upload_url=upload_url, storage_key=key
    )


@router.post("/{rec_id}/complete")
def complete_upload(
    rec_id: uuid.UUID,
    db: Session = Depends(get_db),
    sid: str = Depends(session_id),
):
    """Verify file existence in object storage and enqueue the job for background processing."""
    rec = db.get(Recording, rec_id)
    if not rec or rec.owner_session != sid:
        raise HTTPException(404, "Recording not found")
    if rec.status != Status.UPLOADING:
        return {"status": rec.status}

    exists, size = storage.object_exists(rec.storage_key)
    if not exists:
        set_status(
            db,
            rec,
            Status.FAILED,
            error_code="UPLOAD_INCOMPLETE",
            error_message="The upload did not finish. Please try again.",
        )
        db.commit()
        raise HTTPException(400, "Upload did not complete")

    if size:
        rec.size_bytes = size
    set_status(db, rec, Status.QUEUED, {"size_bytes": size})
    rec.next_attempt_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": rec.status}


@router.get("", response_model=list[RecordingListItem])
def list_recordings(
    db: Session = Depends(get_db),
    sid: str = Depends(session_id),
    limit: int = Query(50, le=100),
    offset: int = 0,
):
    """List recordings associated with the current session."""
    rows = db.scalars(
        select(Recording)
        .where(Recording.owner_session == sid)
        .order_by(Recording.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return rows


@router.get("/{rec_id}", response_model=RecordingDetail)
def get_recording(
    rec_id: uuid.UUID,
    db: Session = Depends(get_db),
    sid: str = Depends(session_id),
):
    """Retrieve full details, status, transcript, and summary for a single recording."""
    rec = db.get(Recording, rec_id)
    if not rec or rec.owner_session != sid:
        raise HTTPException(404, "Recording not found")

    audio_url = None
    try:
        if rec.status != Status.UPLOADING:
            audio_url = storage.create_signed_download_url(rec.storage_key, 3600)
    except storage.StorageError:
        pass

    return RecordingDetail(
        id=rec.id,
        filename=rec.filename,
        status=rec.status,
        language_code=rec.language_code,
        duration_seconds=rec.duration_seconds,
        created_at=rec.created_at,
        error_code=rec.error_code,
        error_message=rec.error_message,
        attempts=rec.attempts,
        transcript=rec.transcript.full_text if rec.transcript else None,
        segments=rec.transcript.segments if rec.transcript else None,
        summary=rec.summary.content if rec.summary else None,
        audio_url=audio_url,
        events=rec.events,
    )


@router.post("/{rec_id}/retry")
def retry(
    rec_id: uuid.UUID,
    db: Session = Depends(get_db),
    sid: str = Depends(session_id),
):
    """Reset a failed or completed recording job to re-run processing."""
    rec = db.get(Recording, rec_id)
    if not rec or rec.owner_session != sid:
        raise HTTPException(404, "Recording not found")
    if rec.status not in (Status.FAILED, Status.NO_SPEECH, Status.COMPLETE):
        raise HTTPException(409, f"Cannot retry while status is {rec.status}")

    rec.attempts = 0
    rec.next_attempt_at = datetime.now(timezone.utc)
    target = Status.TRANSCRIBED if rec.transcript else Status.QUEUED
    if target == Status.QUEUED:
        rec.provider_job_id = None
    set_status(db, rec, target, {"trigger": "manual_retry"})
    db.commit()
    return {"status": rec.status}