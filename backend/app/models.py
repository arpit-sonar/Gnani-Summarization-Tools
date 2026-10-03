"""SQLAlchemy ORM models mirroring migrations/001_init.sql."""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Status:
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSCRIBED = "TRANSCRIBED"
    SUMMARIZING = "SUMMARIZING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    NO_SPEECH = "NO_SPEECH"

    TERMINAL = {COMPLETE, FAILED, NO_SPEECH}


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    filename: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    language_code: Mapped[str] = mapped_column(Text, default="en-IN")
    storage_key: Mapped[str] = mapped_column(Text)

    # Workflow tracking
    status: Mapped[str] = mapped_column(Text, default=Status.UPLOADING)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Worker queue control fields
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    provider_job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_session: Mapped[str] = mapped_column(Text)

    # Relationships
    transcript = relationship(
        "Transcript",
        uselist=False,
        cascade="all, delete-orphan",
        back_populates="recording",
    )
    summary = relationship(
        "Summary",
        uselist=False,
        cascade="all, delete-orphan",
        back_populates="recording",
    )
    events = relationship(
        "JobEvent", cascade="all, delete-orphan", order_by="JobEvent.created_at"
    )


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recordings.id", ondelete="CASCADE"),
        unique=True,
    )
    full_text: Mapped[str] = mapped_column(Text)
    segments: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    language_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    recording = relationship("Recording", back_populates="transcript")


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recordings.id", ondelete="CASCADE"),
        unique=True,
    )
    content: Mapped[dict] = mapped_column(JSONB)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    recording = relationship("Recording", back_populates="summary")


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    recording_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recordings.id", ondelete="CASCADE")
    )
    from_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_status: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )