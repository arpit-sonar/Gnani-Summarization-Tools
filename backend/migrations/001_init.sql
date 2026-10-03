create extension if not exists "pgcrypto";

create table if not exists recordings (
    id               uuid primary key default gen_random_uuid(),
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),

    filename         text        not null,
    content_type     text,
    size_bytes       bigint,
    duration_seconds numeric,
    language_code    text        not null default 'en-IN',
    storage_key      text        not null,

    status           text        not null default 'UPLOADING',
    error_code       text,
    error_message    text,

    attempts         int         not null default 0,
    next_attempt_at  timestamptz not null default now(),
    heartbeat_at     timestamptz,

    provider_job_id  text,
    owner_session    text        not null
);

create index if not exists recordings_owner_idx
    on recordings (owner_session, created_at desc);

create index if not exists recordings_claim_idx
    on recordings (status, next_attempt_at);

create table if not exists transcripts (
    id               uuid primary key default gen_random_uuid(),
    recording_id     uuid not null unique references recordings(id) on delete cascade,
    full_text        text not null,
    segments         jsonb,
    provider         text,
    model            text,
    language_code    text,
    duration_seconds numeric,
    created_at       timestamptz not null default now()
);

create table if not exists summaries (
    id             uuid primary key default gen_random_uuid(),
    recording_id   uuid not null unique references recordings(id) on delete cascade,
    content        jsonb not null,
    model          text,
    prompt_version text,
    created_at     timestamptz not null default now()
);

create table if not exists job_events (
    id           bigserial primary key,
    recording_id uuid not null references recordings(id) on delete cascade,
    from_status  text,
    to_status    text not null,
    detail       jsonb,
    created_at   timestamptz not null default now()
);
create index if not exists job_events_recording_idx
    on job_events (recording_id, created_at);
