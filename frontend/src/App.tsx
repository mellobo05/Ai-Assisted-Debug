import React, { useMemo, useState } from "react";
import {
  getApiBase,
  jiraAnalyze,
  getJiraAnalyzeJob,
  type JiraAnalyzeRequest,
  type JiraAnalyzeResponse,
} from "./api";

const OS_OPTIONS = [
  { value: "windows", label: "Windows" },
  { value: "linux", label: "Linux" },
  { value: "chromeos", label: "ChromeOS" },
  { value: "macos", label: "macOS" },
  { value: "android", label: "Android" },
  { value: "ios", label: "iOS" }
];

function detectOs(): string {
  try {
    const ua = (navigator.userAgent || "").toLowerCase();
    const platform = (navigator.platform || "").toLowerCase();

    // ChromeOS often contains "CrOS"
    if (ua.includes("cros")) return "chromeos";

    if (ua.includes("android")) return "android";
    if (ua.includes("iphone") || ua.includes("ipad") || ua.includes("ipod")) return "ios";

    if (platform.includes("win") || ua.includes("windows")) return "windows";
    if (platform.includes("mac") || ua.includes("mac os")) return "macos";
    if (platform.includes("linux") || ua.includes("linux")) return "linux";
  } catch {
    // ignore
  }
  return "windows";
}

export function App() {
  const [jiraForm, setJiraForm] = useState<JiraAnalyzeRequest>(() => ({
    issue_key: "",
    summary: "",
    component: "",
    os: detectOs(),
    logs: "",
    notes: "",
    external_knowledge: false,
    min_local_score: 0.62,
    analysis_mode: "async"
  }));
  const [isJiraAnalyzing, setIsJiraAnalyzing] = useState(false);
  const [jiraOut, setJiraOut] = useState<JiraAnalyzeResponse | null>(null);
  const [jiraErr, setJiraErr] = useState<string | null>(null);

  const apiBase = useMemo(() => getApiBase(), []);

  const canJiraAnalyze =
    (jiraForm.issue_key || "").trim().length > 0 &&
    (jiraForm.summary || "").trim().length > 0 &&
    !isJiraAnalyzing;

  async function readFileAsText(file: File): Promise<string> {
    return await new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onerror = () => reject(new Error("Failed to read file"));
      r.onload = () => resolve(String(r.result ?? ""));
      r.readAsText(file);
    });
  }

  async function onJiraAnalyze(e: React.FormEvent) {
    e.preventDefault();
    setJiraErr(null);
    setJiraOut(null);
    setIsJiraAnalyzing(true);
    try {
      const resp = await jiraAnalyze({
        issue_key: (jiraForm.issue_key || "").trim().toUpperCase(),
        summary: (jiraForm.summary || "").trim(),
        component: jiraForm.component?.trim() || null,
        os: jiraForm.os?.trim() || null,
        logs: jiraForm.logs?.trim() || null,
        notes: jiraForm.notes?.trim() || null,
        external_knowledge: Boolean(jiraForm.external_knowledge),
        min_local_score: Number(jiraForm.min_local_score ?? 0.62),
        analysis_mode: (jiraForm.analysis_mode ?? "async") as any
      });
      setJiraOut(resp);

      // If analysis is async, poll until completed (or timeout).
      const jobId = resp.job_id;
      const status = (resp.analysis_status || "").toUpperCase();
      if (jobId && status === "PROCESSING") {
        const startedAt = Date.now();
        const maxWaitMs = 45000;
        while (Date.now() - startedAt < maxWaitMs) {
          await new Promise((r) => setTimeout(r, 1000));
          const j = await getJiraAnalyzeJob(jobId);
          setJiraOut(j);
          const s = (j.analysis_status || "").toUpperCase();
          if (s && s !== "PROCESSING") break;
        }
      }
    } catch (err: any) {
      setJiraErr(err?.message ?? String(err));
    } finally {
      setIsJiraAnalyzing(false);
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
          <div className="cardTitle">JIRA Analyze (one-step)</div>
          <div className="muted">
            One input set: if the issue exists and a prior analysis exists, you’ll get a cached RCA. Otherwise it
            stores/updates the issue, finds related issues, returns a fast report, and computes analysis in background.
          </div>

          <form onSubmit={onJiraAnalyze} className="form">
            <div className="row">
              <div className="field">
                <label className="label" htmlFor="jiraKey">
                  JIRA ID
                </label>
                <input
                  id="jiraKey"
                  className="input"
                  placeholder="e.g. SYSCROS-123456"
                  value={jiraForm.issue_key || ""}
                  onChange={(e) => setJiraForm((s) => ({ ...s, issue_key: e.target.value.toUpperCase() }))}
                />
              </div>

              <div className="field">
                <label className="label" htmlFor="jiraOs">
                  OS
                </label>
                <select
                  id="jiraOs"
                  className="select"
                  value={jiraForm.os ?? detectOs()}
                  onChange={(e) => setJiraForm((s) => ({ ...s, os: e.target.value }))}
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
              <label className="label" htmlFor="jiraSummary">
                JIRA summary
              </label>
              <input
                id="jiraSummary"
                className="input"
                placeholder="e.g. Video flicker during playback"
                value={jiraForm.summary || ""}
                onChange={(e) => setJiraForm((s) => ({ ...s, summary: e.target.value }))}
              />
            </div>

            <div className="row">
              <div className="field">
                <label className="label" htmlFor="jiraComponent">
                  Component
                </label>
                <input
                  id="jiraComponent"
                  className="input"
                  placeholder="e.g. Display"
                  value={jiraForm.component ?? ""}
                  onChange={(e) => setJiraForm((s) => ({ ...s, component: e.target.value }))}
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="jiraLogsFile">
                  Logs file (optional)
                </label>
                <input
                  id="jiraLogsFile"
                  className="input"
                  type="file"
                  accept=".txt,.log"
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    const text = await readFileAsText(f);
                    setJiraForm((s) => ({ ...s, logs: text }));
                  }}
                />
              </div>
            </div>

            <div className="field">
              <label className="label" htmlFor="jiraLogs">
                Logs
              </label>
              <textarea
                id="jiraLogs"
                className="textarea"
                placeholder="Paste relevant logs here…"
                value={jiraForm.logs ?? ""}
                onChange={(e) => setJiraForm((s) => ({ ...s, logs: e.target.value }))}
                rows={6}
              />
            </div>

            <div className="row">
              <div className="field">
                <label className="label" htmlFor="jiraExternal">
                  External knowledge
                </label>
                <select
                  id="jiraExternal"
                  className="select"
                  value={jiraForm.external_knowledge ? "yes" : "no"}
                  onChange={(e) => setJiraForm((s) => ({ ...s, external_knowledge: e.target.value === "yes" }))}
                >
                  <option value="no">No</option>
                  <option value="yes">Yes (if similarity &lt; threshold)</option>
                </select>
              </div>
              <div className="field">
                <label className="label" htmlFor="jiraMinScore">
                  Similarity threshold
                </label>
                <input
                  id="jiraMinScore"
                  className="input"
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={Number(jiraForm.min_local_score ?? 0.62)}
                  onChange={(e) => setJiraForm((s) => ({ ...s, min_local_score: Number(e.target.value || 0.62) }))}
                />
              </div>
            </div>

            <div className="field">
              <label className="label" htmlFor="jiraNotes">
                Important info / notes (optional)
              </label>
              <textarea
                id="jiraNotes"
                className="textarea"
                placeholder="Any extra hints: repro steps, environment, codec, driver version…"
                value={jiraForm.notes ?? ""}
                onChange={(e) => setJiraForm((s) => ({ ...s, notes: e.target.value }))}
                rows={4}
              />
            </div>

            <div className="row">
              <div className="field">
                <label className="label" htmlFor="jiraMode">
                  Analysis mode
                </label>
                <select
                  id="jiraMode"
                  className="select"
                  value={jiraForm.analysis_mode ?? "async"}
                  onChange={(e) =>
                    setJiraForm((s) => ({ ...s, analysis_mode: e.target.value as any }))
                  }
                >
                  <option value="async">Async (fast UI)</option>
                  <option value="sync">Sync (wait for analysis)</option>
                  <option value="skip">Skip analysis (report only)</option>
                </select>
              </div>
              <div className="field">
                <label className="label">&nbsp;</label>
                <button className="button" disabled={!canJiraAnalyze} type="submit">
                  {isJiraAnalyzing ? "Analyzing…" : "Analyze"}
                </button>
              </div>
            </div>

            <div className="actions">
              <button
                className="buttonSecondary"
                type="button"
                onClick={() => {
                  setJiraOut(null);
                  setJiraErr(null);
                }}
                disabled={isJiraAnalyzing}
              >
                Clear output
              </button>
            </div>
          </form>

          {jiraErr && (
            <div className="errorBox">
              <div className="errorTitle">Analyze failed</div>
              <pre className="pre">{jiraErr}</pre>
            </div>
          )}

          {jiraOut && (
            <div className="resultBox">
              {jiraOut.cache_hit ? (
                <div className="hint">
                  Cache hit: returned previous RCA for the same JIRA key + summary.
                </div>
              ) : null}
              <div className="kv">
                <div className="k">issue_key</div>
                <div className="v">
                  <code>{jiraOut.issue_key}</code>
                </div>
              </div>
              {"analysis_status" in jiraOut ? (
                <div className="kv">
                  <div className="k">analysis_status</div>
                  <div className="v">
                    <code>{String(jiraOut.analysis_status ?? "")}</code>
                  </div>
                </div>
              ) : null}
              {jiraOut.related_issue_keys && jiraOut.related_issue_keys.length > 0 ? (
                <div className="kv">
                  <div className="k">related</div>
                  <div className="v">
                    <code>{jiraOut.related_issue_keys.join(", ")}</code>
                  </div>
                </div>
              ) : null}
              <div className="hint">Report</div>
              <pre className="pre">{jiraOut.report}</pre>
              <div className="hint">Analysis</div>
              <pre className="pre">{jiraOut.analysis}</pre>
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

