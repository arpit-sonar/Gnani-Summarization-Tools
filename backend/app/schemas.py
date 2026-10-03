import uuid
from datetime import datetime

from pydantic import BaseModel, Field

ALLOWED_EXTENSIONS = {"wav", "mp3", "ogg", "flac", "aac", "m4a", "mp4", "webm"}
ALLOWED_LANGUAGES = ["en-IN", "hi-IN", "bn-IN", "kn-IN", "ml-IN", "mr-IN", "ta-IN", "te-IN"]


class PresignRequest(BaseModel):
    filename: str
    content_type: str | None = None
    size_bytes: int = Field(gt=0)
    language_code: str = "en-IN"


class PresignResponse(BaseModel):
    recording_id: uuid.UUID
    upload_url: str
    storage_key: str


class EventOut(BaseModel):
    to_status: str
    detail: dict | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class RecordingListItem(BaseModel):
    id: uuid.UUID
    filename: str
    status: str
    language_code: str
    duration_seconds: float | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class RecordingDetail(RecordingListItem):
    error_code: str | None = None
    error_message: str | None = None
    attempts: int = 0
    transcript: str | None = None
    segments: list | None = None
    summary: dict | None = None
    audio_url: str | None = None
    events: list[EventOut] = []