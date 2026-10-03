from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from . import gnani, llm, storage
from .config import settings
from .db import session_scope
from .events import set_status
from .models import Recording, Status, Summary, Transcript

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
log = logging.getLogger("worker")

_running = True


def _stop(*_):
    global _running
    log.info("shutdown signal received, finishing current job")
    _running = False


CLAIM_SQL = text("""
UPDATE recordings
   SET status = CASE status
                  WHEN 'QUEUED'      THEN 'TRANSCRIBING'
                  WHEN 'TRANSCRIBED' THEN 'SUMMARIZING'
                END,
       heartbeat_at = now(),
       updated_at   = now()
 WHERE id = (
       SELECT id FROM recordings
        WHERE status IN ('QUEUED', 'TRANSCRIBED')
          AND next_attempt_at <= now()
        ORDER BY created_at
        LIMIT 1
        FOR UPDATE SKIP LOCKED
 )
RETURNING id, status;
""")

REAP_SQL = text("""
UPDATE recordings
   SET status = CASE status
                  WHEN 'TRANSCRIBING' THEN 'QUEUED'
                  WHEN 'SUMMARIZING'  THEN 'TRANSCRIBED'
                END,
       heartbeat_at = NULL,
       updated_at   = now()
 WHERE status IN ('TRANSCRIBING', 'SUMMARIZING')
   AND heartbeat_at < now() - make_interval(secs => :stale)
RETURNING id;
""")


def reap_stale(db) -> None:
    rows = db.execute(REAP_SQL, {"stale": settings.STALE_HEARTBEAT_SECONDS}).all()
    for (rid,) in rows:
        log.warning(f"reaped stale job {rid}")


def beat(db, rec: Recording) -> None:
    rec.heartbeat_at = datetime.now(timezone.utc)
    db.flush()


def fail_or_retry(
    db, rec: Recording, code: str, message: str, retryable: bool
) -> None:
    rec.attempts += 1
    if retryable and rec.attempts < settings.MAX_ATTEMPTS:
        delay = min(300, 15 * (2 ** (rec.attempts - 1)))
        rec.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        back = (
            Status.QUEUED if rec.status == Status.TRANSCRIBING else Status.TRANSCRIBED
        )
        set_status(
            db,
            rec,
            back,
            {"retry_in_seconds": delay, "attempt": rec.attempts, "reason": code},
        )
        log.warning(f"{rec.id} {code} -> retry {rec.attempts} in {delay}s")
    else:
        set_status(
            db,
            rec,
            Status.FAILED,
            {"attempt": rec.attempts},
            error_code=code,
            error_message=message,
        )
        log.error(f"{rec.id} {code} -> FAILED: {message}")


def run_transcription(db, rec: Recording) -> None:
    audio_url = storage.create_signed_download_url(rec.storage_key, 7200)

    if not rec.provider_job_id:
        job_id = gnani.create_job(audio_url, rec.language_code)
        rec.provider_job_id = job_id
        db.flush()
        gnani.start_job(job_id)
        set_status(db, rec, Status.TRANSCRIBING, {"gnani_job_id": job_id})
        db.commit()
    else:
        job_id = rec.provider_job_id

    deadline = time.time() + settings.JOB_TIMEOUT_SECONDS
    status = None

    while time.time() < deadline and _running:
        time.sleep(settings.POLL_INTERVAL_SECONDS)
        job = gnani.get_job(job_id)
        status = job.get("status")
        progress = job.get("progress", {})
        beat(db, rec)
        db.commit()
        log.info(f"{rec.id} gnani={status} progress={progress}")
        if status in gnani.TERMINAL_STATUSES:
            break
    else:
        if status not in gnani.TERMINAL_STATUSES:
            fail_or_retry(
                db,
                rec,
                "TRANSCRIPTION_TIMEOUT",
                "Transcription took too long and was abandoned.",
                retryable=True,
            )
            return

    if status in ("FAILED", "START_FAILED", "CANCELLED"):
        reason = (
            gnani.get_job(job_id).get("cancel_reason")
            or "The transcription service could not process this file."
        )
        rec.provider_job_id = None
        fail_or_retry(db, rec, "TRANSCRIPTION_FAILED", reason, retryable=False)
        return

    files = gnani.get_job_files(job_id)
    done = [
        f for f in files if f.get("status") == "COMPLETED" and f.get("transcript_url")
    ]

    if not done:
        err = next(
            (f.get("error_message") for f in files if f.get("error_message")),
            "No speech was detected in this file.",
        )
        set_status(
            db,
            rec,
            Status.NO_SPEECH,
            {"gnani_error": err},
            error_code="NO_SPEECH",
            error_message=err,
        )
        return

    data = gnani.download_transcript(done[0]["transcript_url"])
    full = (data.get("full_transcript") or "").strip()

    if not full:
        set_status(
            db,
            rec,
            Status.NO_SPEECH,
            error_code="NO_SPEECH",
            error_message="No speech was detected in this file.",
        )
        return

    db.add(
        Transcript(
            recording_id=rec.id,
            full_text=full,
            segments=data.get("segments"),
            provider="gnani",
            model=data.get("model"),
            language_code=data.get("language_code"),
            duration_seconds=data.get("duration_seconds"),
        )
    )
    rec.duration_seconds = data.get("duration_seconds")
    rec.attempts = 0
    set_status(
        db,
        rec,
        Status.TRANSCRIBED,
        {"chars": len(full), "segments": len(data.get("segments") or [])},
    )


def run_summary(db, rec: Recording) -> None:
    if not rec.transcript:
        set_status(
            db,
            rec,
            Status.FAILED,
            error_code="NO_TRANSCRIPT",
            error_message="Internal error: transcript missing.",
        )
        return

    content = llm.summarise(rec.transcript.full_text)
    db.add(
        Summary(
            recording_id=rec.id,
            content=content,
            model=settings.GEMINI_MODEL,
            prompt_version=llm.PROMPT_VERSION,
        )
    )
    set_status(db, rec, Status.COMPLETE)


def process_one() -> bool:
    with session_scope() as db:
        reap_stale(db)
        row = db.execute(CLAIM_SQL).first()
        if not row:
            return False
        rec_id, claimed_status = row
        db.commit()

    with session_scope() as db:
        rec = db.get(Recording, rec_id)
        log.info(f"claimed {rec.id} as {claimed_status}")
        try:
            if claimed_status == Status.TRANSCRIBING:
                run_transcription(db, rec)
            else:
                run_summary(db, rec)
        except gnani.GnaniError as e:
            fail_or_retry(db, rec, e.code, str(e), e.retryable)
        except llm.LLMError as e:
            fail_or_retry(
                db,
                rec,
                "SUMMARY_FAILED",
                "The summary could not be generated.",
                e.retryable,
            )
        except Exception as e:
            log.exception("unexpected worker error")
            fail_or_retry(db, rec, "INTERNAL_ERROR", str(e)[:300], retryable=True)

    return True


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("worker started")

    while _running:
        try:
            if not process_one():
                time.sleep(3)
        except Exception:
            log.exception("loop error")
            time.sleep(5)

    log.info("worker stopped")
    sys.exit(0)


if __name__ == "__main__":
    main()