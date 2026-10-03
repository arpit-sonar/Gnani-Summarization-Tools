"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  completeUpload,
  listRecordings,
  presign,
  uploadToBucket,
  type RecordingListItem,
} from "@/lib/api";

const LANGUAGES = [
  ["en-IN", "English (India)"],
  ["hi-IN", "Hindi"],
  ["bn-IN", "Bengali"],
  ["kn-IN", "Kannada"],
  ["ml-IN", "Malayalam"],
  ["mr-IN", "Marathi"],
  ["ta-IN", "Tamil"],
  ["te-IN", "Telugu"],
];

function getBadgeClass(status: string): string {
  if (status === "COMPLETE") return "badge ok";
  if (status === "FAILED" || status === "NO_SPEECH") return "badge err";
  if (status === "UPLOADING") return "badge";
  return "badge run";
}

export default function Home() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);

  const [items, setItems] = useState<RecordingListItem[]>([]);
  const [lang, setLang] = useState("en-IN");
  const [busy, setBusy] = useState(false);
  const [pct, setPct] = useState(0);
  const [phase, setPhase] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const refresh = () => listRecordings().then(setItems).catch(() => {});

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, []);

  async function onUpload() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;

    setErr(null);
    setBusy(true);
    setPct(0);

    try {
      setPhase("Preparing upload…");
      const { recording_id, upload_url } = await presign({
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        size_bytes: file.size,
        language_code: lang,
      });

      setPhase("Uploading…");
      await uploadToBucket(upload_url, file, setPct);

      setPhase("Queuing…");
      await completeUpload(recording_id);

      router.push(`/r/${recording_id}`);
    } catch (e: any) {
      setErr(e.message || "Something went wrong");
    } finally {
      setBusy(false);
      setPhase("");
    }
  }

  return (
    <>
      <div className="card">
        <h2>Upload a recording</h2>
        <div className="row">
          <input
            ref={fileRef}
            type="file"
            accept=".wav,.mp3,.m4a,.ogg,.flac,.aac,audio/*"
            disabled={busy}
          />
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            disabled={busy}
          >
            {LANGUAGES.map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
          <button className="btn" onClick={onUpload} disabled={busy}>
            {busy ? "Working…" : "Transcribe"}
          </button>
        </div>

        <p className="muted">
          WAV, MP3, M4A, OGG, FLAC or AAC · up to 100 MB · any length
        </p>

        {busy && (
          <>
            <div className="bar">
              <i style={{ width: `${pct}%` }} />
            </div>
            <p className="muted">
              {phase} {pct > 0 && pct < 100 ? `${pct}%` : ""}
            </p>
          </>
        )}

        {err && (
          <div className="card err-box">
            <strong>Upload failed.</strong>
            <p className="muted">{err}</p>
            <button className="btn ghost" onClick={onUpload}>
              Try again
            </button>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Past uploads</h2>
        {items.length === 0 && <p className="muted">Nothing here yet.</p>}
        <ul className="list">
          {items.map((r) => (
            <li key={r.id}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <Link href={`/r/${r.id}`}>{r.filename}</Link>
                <div className="muted">
                  {new Date(r.created_at).toLocaleString()} · {r.language_code}
                  {r.duration_seconds
                    ? ` · ${Math.round(Number(r.duration_seconds))}s`
                    : ""}
                </div>
              </div>
              <span className={getBadgeClass(r.status)}>
                {r.status.toLowerCase()}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}