from __future__ import annotations

import json
import httpx

from .config import settings

PROMPT_VERSION = "v1"
MAX_TRANSCRIPT_CHARS = 400_000

SYSTEM_PROMPT = """You summarise transcripts of audio recordings.

The text you receive was produced by an automatic speech recognition system.
It may contain recognition errors, missing punctuation, and no capitalisation.

Rules:
- Use ONLY information present in the transcript. Never invent names, numbers, dates, decisions or outcomes.
- If the transcript is too short, unclear or garbled to summarise, say so in the tl_dr and leave the other fields empty rather than guessing.
- Do not repeat the same point in more than one field.
- Write in the same language as the transcript.
- Keep the tl_dr to 2-3 sentences.

Return ONLY JSON matching this shape:
{
  "tl_dr": string,
  "key_points": [string],
  "topics": [string],
  "action_items": [{"task": string, "owner": string}],
  "notable_quotes": [string]
}
Omit array entries entirely if there are none - return an empty array."""


class LLMError(RuntimeError):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


def summarise(transcript: str) -> dict:
    text = transcript.strip()
    if len(text) < 40:
        return {
            "tl_dr": "The recording was too short to summarise meaningfully.",
            "key_points": [],
            "topics": [],
            "action_items": [],
            "notable_quotes": [],
        }

    if len(text) > MAX_TRANSCRIPT_CHARS:
        text = text[:MAX_TRANSCRIPT_CHARS]

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent"
    )
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": f"TRANSCRIPT:\n\n{text}"}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(180.0, connect=15.0)) as client:
            r = client.post(url, params={"key": settings.GEMINI_API_KEY}, json=payload)
    except httpx.HTTPError as e:
        raise LLMError(f"network error calling Gemini: {e}", retryable=True)

    if r.status_code == 429:
        raise LLMError("Gemini rate limit", retryable=True)
    if r.status_code >= 500:
        raise LLMError(f"Gemini {r.status_code}", retryable=True)
    if r.status_code >= 400:
        raise LLMError(f"Gemini rejected request: {r.text[:300]}", retryable=False)

    try:
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(raw)
    except Exception as e:
        raise LLMError(f"could not parse Gemini response: {e}", retryable=True)

    return {
        "tl_dr": data.get("tl_dr", ""),
        "key_points": data.get("key_points", []) or [],
        "topics": data.get("topics", []) or [],
        "action_items": data.get("action_items", []) or [],
        "notable_quotes": data.get("notable_quotes", []) or [],
    }