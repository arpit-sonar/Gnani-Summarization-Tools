# Audio Notes

Upload an audio file, get back a transcript and an AI summary. Past uploads are
saved and can be reopened.

Built as a take-home assignment for Gnani.ai.

- Live app: https://gnani-summarization-tools-bice.vercel.app
- Architecture page: /architecture

## The assignment

Build a web platform where a user uploads an audio file of any length, transcribe
it with Gnani's ASR API, summarise it with an LLM, show both, and keep a list of
past uploads. Required stack: Next.js, FastAPI, Postgres, a storage bucket and
background jobs. It had to be deployed, handle failures visibly, and show progress.

## Features

- Upload WAV, MP3, M4A, OGG, FLAC or AAC up to 100 MB, any duration
- Transcription in 8 Indian languages (English, Hindi, Bengali, Kannada,
  Malayalam, Marathi, Tamil, Telugu)
- Summary with TL;DR, key points, topics and action items
- Live upload progress, then stage-by-stage processing status
- Audio playback alongside the transcript
- List of past uploads, reopen any of them
- Retry button on failed jobs

## Tech used

| Part | Choice |
|---|---|
| Frontend | Next.js 15 (App Router), plain CSS |
| Backend | FastAPI, SQLAlchemy 2.0 (sync) |
| Database | Postgres (Supabase) |
| Storage | Supabase Storage, private bucket |
| Background jobs | Separate worker process, Postgres-backed queue |
| ASR | Gnani Prisma v2.5, Batch STT API |
| LLM | Google Gemini Flash |
| Hosting | Vercel (frontend), Render (API + worker) |

## Architecture

```
Browser → FastAPI: ask for a signed upload URL (file is validated here first)
Browser → Supabase Storage: PUT the audio directly, never through the API
Browser → FastAPI: /complete → verify the object exists → status = QUEUED

Worker (separate process)
  → claims the job from Postgres with SELECT ... FOR UPDATE SKIP LOCKED
  → generates a signed download URL and submits it to Gnani Batch STT
  → polls every 12s until the job finishes, saves the transcript
  → sends the transcript to Gemini, saves the summary

Browser → polls GET /api/recordings/{id} every 2.5s until the job is done
```

Status flow:

```
UPLOADING → QUEUED → TRANSCRIBING → TRANSCRIBED → SUMMARIZING → COMPLETE
                         ↓                ↓
                     NO_SPEECH         FAILED
```

Transcription and summarisation are two separate stages with `TRANSCRIBED` in
between, so they fail independently. If Gemini is down the transcript is still
saved and shown, and only the summary retries.

Everything that calls a third party runs in the background. A three-minute HTTP
request would be killed by the browser or a proxy long before it finished.

I used Postgres as the job queue instead of adding Celery and Redis. Job state has
to be in Postgres anyway for the UI to read it and to survive a redeploy, so a
broker would have meant the same state in two places and another service to deploy.

## Problems I faced

- `POST /stt/v3` rejects anything over 60 seconds. The task asks for 2 minutes+.
  Had to move to the Batch jobs API, which is why there's a worker and a polling
  UI in this project at all.
- Creating a Gnani job doesn't start it. Mine sat at `CREATED` and I blamed my
  polling loop for a while before finding `POST /jobs/{id}/start` in the docs.
- Batch multipart uploads are capped at 10 MB per file. Switched to passing a
  signed URL instead of the bytes, which has no cap.
- My signed URLs were expiring before Gnani fetched the audio, so jobs died with
  `START_FAILED`. Bumped them to 2 hours.
- Restarting the worker left jobs stuck in `TRANSCRIBING` forever. Added a
  heartbeat and a reaper that requeues anything silent for 5 minutes.
- SQLAlchemy needs `postgresql+psycopg://`, and the direct Supabase connection kept
  dropping. Session pooler fixed it.
- Built a percentage progress bar, then deleted it. I don't actually know how far
  along a Gnani job is, so the number was invented. Shows named stages now.

## Failure handling

| Failure | What happens |
|---|---|
| Bad file type or too large | Rejected before any bytes upload |
| Upload drops | Object check fails, nothing is queued, Retry shown |
| Gnani 429 or 5xx | Retried with backoff (15s, 30s, 60s), max 3 attempts |
| Gnani 400 or 403 | Failed immediately — retrying would never succeed |
| Silent audio | Own state `NO_SPEECH` with a plain message, not an error |
| Worker crashes | Heartbeat goes stale, reaper requeues the job |
| LLM fails | Transcript still shown, only the summary retries |

## Project structure

```
backend/app/
  config.py       env vars
  db.py           engine and sessions
  models.py       ORM models and the status state machine
  schemas.py      request/response shapes
  storage.py      Supabase signed upload/download URLs
  gnani.py        Batch STT client, error classification
  llm.py          Gemini summariser
  worker.py       job queue, heartbeat, reaper, retries
  main.py         FastAPI app
  routers/recordings.py
frontend/app/
  page.tsx            upload and past uploads
  r/[id]/page.tsx     transcript, summary, progress
  architecture/page.tsx
```

## Limitations

- No authentication. Uploads are scoped by a session id in localStorage.
- Speaker diarization is off. Gnani supports max 2 speakers; I had no good test file.
- Numbers appear in spoken form, since Gnani's Batch API doesn't support ITN.
- One worker process, so jobs run one at a time.
- No deduplication, so uploading the same file twice transcribes it twice.
- The backend is on a free tier that sleeps after 15 minutes idle, so the first
  request can take about 50 seconds.

## What I'd add next

- Gnani's `callback_url` webhook as a fast path, keeping polling as a fallback
- Deduplicate uploads by file hash so credits aren't spent twice
- Speaker diarization and click-a-line-to-seek playback
- Summary bullets linked back to transcript timestamps
- Real auth and per-user rate limiting
