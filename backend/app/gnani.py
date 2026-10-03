from __future__ import annotations

import httpx

from .config import settings

TERMINAL_STATUSES = {
    "COMPLETED",
    "PARTIAL_FAILURE",
    "FAILED",
    "START_FAILED",
    "CANCELLED",
}

_HEADERS = {"X-API-Key-ID": settings.GNANI_API_KEY}
_TIMEOUT = httpx.Timeout(60.0, connect=15.0)


class GnaniError(RuntimeError):
    def __init__(
        self, message: str, code: str = "GNANI_ERROR", retryable: bool = False
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _check(r: httpx.Response) -> dict:
    if r.status_code < 400:
        return r.json()

    try:
        body = r.json()
        msg = body.get("error", {}).get("message") or body.get("message") or r.text
    except Exception:
        msg = r.text

    if r.status_code == 429:
        raise GnaniError(msg, "RATE_LIMITED", retryable=True)
    if r.status_code in (500, 502, 503, 504):
        raise GnaniError(msg, "UPSTREAM_UNAVAILABLE", retryable=True)
    if r.status_code == 403:
        raise GnaniError(msg, "FORBIDDEN_OR_NO_CREDITS", retryable=False)
    if r.status_code == 401:
        raise GnaniError(msg, "BAD_API_KEY", retryable=False)

    raise GnaniError(msg, "INVALID_REQUEST", retryable=False)


def create_job(
    audio_url: str,
    language_code: str,
    *,
    diarization: bool = False,
    denoise: bool = False,
    bias_list: list[str] | None = None,
) -> str:
    config: dict = {
        "model": "gnani-prisma-v2.5",
        "language_code": language_code,
        "mode": "transcribe",
        "with_denoise": denoise,
    }
    if diarization:
        config["with_diarization"] = True
        config["num_speakers"] = 2
    if bias_list:
        config["bias_list"] = bias_list[:100]
        config["bias_score"] = 1.0

    payload = {
        "config": config,
        "source": {
            "type": "cloud_storage",
            "auth": {"mode": "public"},
            "paths": [audio_url],
        },
    }

    with httpx.Client(timeout=_TIMEOUT) as client:
        url = f"{settings.GNANI_BASE_URL}/stt/v3/batch/jobs"
        data = _check(client.post(url, headers=_HEADERS, json=payload))

    return data["job_id"]


def start_job(job_id: str) -> None:
    with httpx.Client(timeout=_TIMEOUT) as client:
        url = f"{settings.GNANI_BASE_URL}/stt/v3/batch/jobs/{job_id}/start"
        _check(client.post(url, headers=_HEADERS))


def get_job(job_id: str) -> dict:
    with httpx.Client(timeout=_TIMEOUT) as client:
        url = f"{settings.GNANI_BASE_URL}/stt/v3/batch/jobs/{job_id}"
        return _check(client.get(url, headers=_HEADERS))


def get_job_files(job_id: str) -> list[dict]:
    with httpx.Client(timeout=_TIMEOUT) as client:
        url = f"{settings.GNANI_BASE_URL}/stt/v3/batch/jobs/{job_id}/files"
        data = _check(client.get(url, headers=_HEADERS))

    return data.get("data", [])


def download_transcript(transcript_url: str) -> dict:
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
        response = client.get(transcript_url)
        response.raise_for_status()
        return response.json()