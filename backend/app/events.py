"""Status transitions in one place, so every change is audited."""
from sqlalchemy.orm import Session

from .models import JobEvent, Recording


def set_status(db: Session, rec: Recording, new_status: str,
               detail: dict | None = None, *,
               error_code: str | None = None,
               error_message: str | None = None) -> None:
    db.add(JobEvent(recording_id=rec.id, from_status=rec.status,
                    to_status=new_status, detail=detail))
    rec.status = new_status
    rec.error_code = error_code
    rec.error_message = error_message
    db.flush()
