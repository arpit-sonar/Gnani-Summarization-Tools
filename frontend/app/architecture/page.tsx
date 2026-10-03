import Link from "next/link";

const GITHUB_REPO_URL = "https://github.com/arpit-sonar/Gnani-Summarization-Tools";

export default function Architecture() {
  return (
    <div className="card">
      <h2>System Architecture</h2>
      <p className="muted">
        Repository:{" "}
        <a href={GITHUB_REPO_URL} target="_blank" rel="noreferrer">
          {GITHUB_REPO_URL}
        </a>
      </p>

      <h3>Processing Pipeline</h3>
      <p>
        1. The browser requests a signed upload URL from FastAPI after validating the file metadata.<br />
        2. The client uploads audio directly to Supabase Storage, bypassing API body size limits and avoiding proxy timeouts.<br />
        3. The client calls <code>/complete</code> to verify the upload in storage and set the job status to <code>QUEUED</code>.
      </p>

      <h3>Storage & Data Models</h3>
      <p>
        Audio files reside in a private Supabase Storage bucket structured as <code>{"{session}/{recording_id}/original.{ext}"}</code>. Media playback and transcription use short-lived signed URLs. Transcripts, generated summaries, job states, and event logs are stored in PostgreSQL.
      </p>

      <h3>Audio Transcription Workflow</h3>
      <p>
        For audio files longer than 60 seconds, processing uses the provider's Batch API via public signed URLs rather than raw multipart uploads. The worker submits the URL, triggers job execution, polls the status endpoint, and fetches the finished transcript once complete.
      </p>

      <h3>Queue & Worker Process</h3>
      <p>
        PostgreSQL serves as the primary task queue. Background worker processes atomic job allocations using <code>SELECT ... FOR UPDATE SKIP LOCKED</code>, eliminating the need for an external queue broker like Redis or Celery.
      </p>

      <h3>Fault Tolerance & Retries</h3>
      <ul>
        <li><strong>Pre-upload Validation:</strong> Invalid file extensions or sizes fail at the presign stage before uploading.</li>
        <li><strong>Dropped Uploads:</strong> Verified via storage HEAD requests upon completion; failed uploads enable manual retries.</li>
        <li><strong>Transient Errors:</strong> Retried automatically using exponential backoff up to the attempt limit.</li>
        <li><strong>Stale Worker Recovery:</strong> Active workers log regular heartbeats. If a worker process fails, stagnant jobs are re-queued automatically.</li>
        <li><strong>Decoupled Stages:</strong> Transcription and LLM summarization run as distinct pipeline steps, ensuring completed transcripts are preserved even if summarization encounters errors.</li>
      </ul>

      <h3>Future Enhancements</h3>
      <ul>
        <li>Integrate provider webhooks to reduce status polling overhead.</li>
        <li>Stream summarization responses via Server-Sent Events (SSE).</li>
        <li>Deduplicate uploads using file content hashes (SHA-256).</li>
        <li>Implement user authentication and usage rate limiting.</li>
      </ul>

      <p>
        <Link href="/">← Back to app</Link>
      </p>
    </div>
  );
}