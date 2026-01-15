import React, { useMemo, useState } from "react";
import { getApiBase, startDebug, type DebugRequest, type DebugResponse } from "./api";

type FormState = DebugRequest;

const OS_OPTIONS = [
  { value: "windows", label: "Windows" },
  { value: "linux", label: "Linux" },
  { value: "macos", label: "macOS" },
  { value: "android", label: "Android" },
  { value: "ios", label: "iOS" }
];

export function App() {
  const [form, setForm] = useState<FormState>({
    issue_summary: "",
    domain: "",
    os: "windows",
    logs: ""
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<DebugResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const apiBase = useMemo(() => getApiBase(), []);

  const canSubmit =
    form.issue_summary.trim().length > 0 &&
    form.domain.trim().length > 0 &&
    form.os.trim().length > 0 &&
    form.logs.trim().length > 0 &&
    !isSubmitting;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    setIsSubmitting(true);
    try {
      const resp = await startDebug({
        issue_summary: form.issue_summary.trim(),
        domain: form.domain.trim(),
        os: form.os.trim(),
        logs: form.logs.trim()
      });
      setResult(resp);
    } catch (err: any) {
      setError(err?.message ?? String(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="page">
      <header className="header">
        <div>
          <div className="title">AI Assisted Debugger</div>
          <div className="subtitle">
            Send your issue details to the FastAPI backend and start a debug session.
          </div>
        </div>
        <div className="badge">
          <div className="badgeLabel">API</div>
          <div className="badgeValue">{apiBase}</div>
        </div>
      </header>

      <main className="grid">
        <section className="card">
          <div className="cardTitle">New Debug Request</div>
          <form onSubmit={onSubmit} className="form">
            <div className="field">
              <label className="label" htmlFor="issue_summary">
                Issue summary
              </label>
              <input
                id="issue_summary"
                className="input"
                placeholder="e.g. Video flicker during playback"
                value={form.issue_summary}
                onChange={(e) => setForm((s) => ({ ...s, issue_summary: e.target.value }))}
              />
            </div>

            <div className="row">
              <div className="field">
                <label className="label" htmlFor="domain">
                  Domain
                </label>
                <input
                  id="domain"
                  className="input"
                  placeholder="e.g. graphics / network / storage"
                  value={form.domain}
                  onChange={(e) => setForm((s) => ({ ...s, domain: e.target.value }))}
                />
              </div>

              <div className="field">
                <label className="label" htmlFor="os">
                  OS
                </label>
                <select
                  id="os"
                  className="select"
                  value={form.os}
                  onChange={(e) => setForm((s) => ({ ...s, os: e.target.value }))}
                >
                  {OS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="field">
              <label className="label" htmlFor="logs">
                Logs
              </label>
              <textarea
                id="logs"
                className="textarea"
                placeholder="Paste relevant logs here…"
                value={form.logs}
                onChange={(e) => setForm((s) => ({ ...s, logs: e.target.value }))}
                rows={8}
              />
            </div>

            <div className="actions">
              <button className="button" disabled={!canSubmit} type="submit">
                {isSubmitting ? "Submitting…" : "Start debug"}
              </button>
              <button
                className="buttonSecondary"
                type="button"
                onClick={() => {
                  setForm({ issue_summary: "", domain: "", os: "windows", logs: "" });
                  setResult(null);
                  setError(null);
                }}
                disabled={isSubmitting}
              >
                Clear
              </button>
            </div>
          </form>
        </section>

        <section className="card">
          <div className="cardTitle">Result</div>

          {!result && !error && (
            <div className="muted">
              Submit a request to see the created <code>session_id</code> and status.
            </div>
          )}

          {error && (
            <div className="errorBox">
              <div className="errorTitle">Request failed</div>
              <pre className="pre">{error}</pre>
            </div>
          )}

          {result && (
            <div className="resultBox">
              <div className="kv">
                <div className="k">session_id</div>
                <div className="v">
                  <code>{result.session_id}</code>
                </div>
              </div>
              <div className="kv">
                <div className="k">status</div>
                <div className="v">
                  <span className="statusPill">{result.status}</span>
                </div>
              </div>
              <div className="hint">
                The backend runs embedding generation asynchronously. You can check DB tables
                (<code>debug_sessions</code>, <code>debug_embeddings</code>) to see progress.
              </div>
            </div>
          )}
        </section>
      </main>

      <footer className="footer">
        <span>
          Tip: set <code>VITE_API_BASE</code> in <code>frontend/.env</code> if your backend runs
          on a different host/port.
        </span>
      </footer>
    </div>
  );
}

