export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function sessionId(): string {
  if (typeof window === "undefined") return "anonymous";
  let id = localStorage.getItem("session_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("session_id", id);
  }
  return id;
}

async function req<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Session-Id": sessionId(),
      ...(init.headers || {}),
    },
  });

  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      msg = body.detail || msg;
    } catch {}
    throw new Error(msg);
  }

  return res.json();
}

export type Status =
  | "UPLOADING"
  | "UPLOADED"
  | "QUEUED"
  | "TRANSCRIBING"
  | "TRANSCRIBED"
  | "SUMMARIZING"
  | "COMPLETE"
  | "FAILED"
  | "NO_SPEECH";

export interface RecordingListItem {
  id: string;
  filename: string;
  status: Status;
  language_code: string;
  duration_seconds: number | null;
  created_at: string;
}

export interface Summary {
  tl_dr: string;
  key_points: string[];
  topics: string[];
  action_items: { task: string; owner: string }[];
  notable_quotes: string[];
}

export interface RecordingDetail extends RecordingListItem {
  error_code: string | null;
  error_message: string | null;
  attempts: number;
  transcript: string | null;
  segments:
    | { start_time: number; end_time: number; text: string; speaker_id: number }[]
    | null;
  summary: Summary | null;
  audio_url: string | null;
  events: { to_status: string; detail: any; created_at: string }[];
}

export const listRecordings = () => req<RecordingListItem[]>("/api/recordings");

export const getRecording = (id: string) =>
  req<RecordingDetail>(`/api/recordings/${id}`);

export const retryRecording = (id: string) =>
  req<{ status: Status }>(`/api/recordings/${id}/retry`, { method: "POST" });

export const presign = (body: {
  filename: string;
  content_type: string;
  size_bytes: number;
  language_code: string;
}) =>
  req<{ recording_id: string; upload_url: string; storage_key: string }>(
    "/api/recordings/presign",
    {
      method: "POST",
      body: JSON.stringify(body),
    }
  );

export const completeUpload = (id: string) =>
  req<{ status: Status }>(`/api/recordings/${id}/complete`, { method: "POST" });

export function uploadToBucket(
  url: string,
  file: File,
  onProgress: (pct: number) => void
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    xhr.setRequestHeader("x-upsert", "true");

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new Error(`Upload failed (${xhr.status})`));

    xhr.onerror = () => reject(new Error("Network error during upload"));
    xhr.ontimeout = () => reject(new Error("Upload timed out"));

    xhr.send(file);
  });
}