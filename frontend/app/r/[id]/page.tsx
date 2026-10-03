"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { getRecording, retryRecording, type RecordingDetail } from "@/lib/api";

const STAGES = [
  {
    key: "upload",
    label: "Uploaded",
    reached: [
      "UPLOADED",
      "QUEUED",
      "TRANSCRIBING",
      "TRANSCRIBED",
      "SUMMARIZING",
      "COMPLETE",
      "NO_SPEECH",
    ],
  },
  {
    key: "queue",
    label: "Queued",
    reached: [
      "QUEUED",
      "TRANSCRIBING",
      "TRANSCRIBED",
      "SUMMARIZING",
      "COMPLETE",
      "NO_SPEECH",
    ],
  },
  {
    key: "transcribe",
    label: "Transcribing",
    reached: ["TRANSCRIBED", "SUMMARIZING", "COMPLETE", "NO_SPEECH"],
  },
  {
    key: "summarize",
    label: "Summarising",
    reached: ["COMPLETE"],
  },
];

const ACTIVE_STAGE_MAP: Record<string, string> = {
  QUEUED: "transcribe",
  TRANSCRIBING: "transcribe",
  TRANSCRIBED: "summarize",
  SUMMARIZING: "summarize",
};

const RUNNING_STATUSES = [
  "UPLOADING",
  "UPLOADED",
  "QUEUED",
  "TRANSCRIBING",
  "TRANSCRIBED",
  "SUMMARIZING",
];

export default function Detail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [recording, setRecording] = useState<RecordingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    let active = true;
    let pollTimer: NodeJS.Timeout;

    const fetchRecording = async () => {
      try {
        const data = await getRecording(id);
        if (!active) return;

        setRecording(data);
        setError(null);

        if (RUNNING_STATUSES.includes(data.status)) {
          pollTimer = setTimeout(fetchRecording, 2500);
        }
      } catch (e: any) {
        if (!active) return;
        setError(e.message || "Failed to load recording details.");
        pollTimer = setTimeout(fetchRecording, 5000);
      }
    };

    fetchRecording();

    const secondTimer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);

    return () => {
      active = false;
      clearTimeout(pollTimer);
      clearInterval(secondTimer);
    };
  }, [id]);

  if (error && !recording) {
    return <div className="card err-box">Could not load: {error}</div>;
  }

  if (!recording) {
    return <div className="card muted">Loading…</div>;
  }

  const isFailed = recording.status === "FAILED" || recording.status === "NO_SPEECH";
  const isRunning = RUNNING_STATUSES.includes(recording.status);

  return (
    <>
      <p>
        <Link href="/">← All recordings</Link>
      </p>

      <div className="card">
        <h2>{recording.filename}</h2>
        <p className="muted">
          {new Date(recording.created_at).toLocaleString()} · {recording.language_code}
          {recording.duration_seconds
            ? ` · ${Math.round(Number(recording.duration_seconds))}s audio`
            : ""}
        </p>

        <div className="steps">
          {STAGES.map((stage) => {
            const done = stage.reached.includes(recording.status);
            const active = !done && ACTIVE_STAGE_MAP[recording.status] === stage.key;
            const isStageFailed = isFailed && !done && ACTIVE_STAGE_MAP[recording.status] === stage.key;

            let stepClass = "todo";
            if (isStageFailed) stepClass = "fail";
            else if (done) stepClass = "done";
            else if (active) stepClass = "active";

            return (
              <div key={stage.key} className={`step ${stepClass}`}>
                <span className="dot" />
                <span>{stage.label}</span>
                {active && <span className="muted">· in progress</span>}
              </div>
            );
          })}
        </div>

        {isRunning && (
          <p className="muted">
            Processing in progress ({elapsedSeconds}s elapsed). Long recordings may take a few minutes.
          </p>
        )}
      </div>

      {isFailed && (
        <div className="card err-box">
          <strong>
            {recording.status === "NO_SPEECH" ? "No speech detected" : "Something went wrong"}
          </strong>
          <p className="muted">
            {recording.error_message || "Unknown error."}
          </p>
          <p className="muted">
            <code>{recording.error_code}</code> · {recording.attempts} attempt(s)
          </p>
          <button
            className="btn"
            onClick={() => retryRecording(id).then(() => window.location.reload())}
          >
            Retry
          </button>
        </div>
      )}

      {recording.audio_url && (
        <div className="card">
          <audio controls src={recording.audio_url} style={{ width: "100%" }} />
        </div>
      )}

      {recording.summary && (
        <div className="card">
          <h2>Summary</h2>
          <p>{recording.summary.tl_dr}</p>

          {recording.summary.key_points?.length > 0 && (
            <>
              <h3>Key points</h3>
              <ul>
                {recording.summary.key_points.map((point, idx) => (
                  <li key={idx}>{point}</li>
                ))}
              </ul>
            </>
          )}

          {recording.summary.action_items?.length > 0 && (
            <>
              <h3>Action items</h3>
              <ul>
                {recording.summary.action_items.map((item, idx) => (
                  <li key={idx}>
                    {item.task}
                    {item.owner ? ` — ${item.owner}` : ""}
                  </li>
                ))}
              </ul>
            </>
          )}

          {recording.summary.topics?.length > 0 && (
            <>
              <h3>Topics</h3>
              <p className="muted">{recording.summary.topics.join(" · ")}</p>
            </>
          )}

          <p className="muted">
            AI-generated summary based on machine transcription.
          </p>
        </div>
      )}

      {recording.transcript ? (
        <div className="card">
          <h2>Transcript</h2>
          <pre className="tx">{recording.transcript}</pre>
        </div>
      ) : isRunning ? (
        <div className="card muted">Transcript will appear here when ready.</div>
      ) : null}
    </>
  );
}