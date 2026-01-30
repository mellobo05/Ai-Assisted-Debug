import React, { useMemo, useState } from "react";
import {
  getApiBase,
  getDebugStatus,
  jiraIntake,
  jiraSummarize,
  searchJira,
  startDebug,
  type DebugRequest,
  type DebugResponse,
  type JiraIntakeRequest,
  type JiraSummarizeResponse,
  type JiraSearchResult
} from "./api";

type FormState = DebugRequest;

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
  const [form, setForm] = useState<FormState>(() => ({
    issue_summary: "",
    domain: "",
    os: detectOs(),
    logs: ""
  }));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<DebugResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchLimit, setSearchLimit] = useState(5);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<JiraSearchResult[]>([]);

  const [jiraIntakeForm, setJiraIntakeForm] = useState<JiraIntakeRequest>(() => ({
    issue_key: "",
    summary: "",
    domain: "",
    os: detectOs(),
    logs: ""
  }));
  const [isJiraIntaking, setIsJiraIntaking] = useState(false);
  const [jiraIntakeResult, setJiraIntakeResult] = useState<any>(null);
  const [jiraIntakeError, setJiraIntakeError] = useState<string | null>(null);

  const [jiraKeyToSummarize, setJiraKeyToSummarize] = useState("");
  const [jiraSummDomain, setJiraSummDomain] = useState<string>("");
  const [jiraSummOs, setJiraSummOs] = useState<string>(detectOs());
  const [jiraSummLogs, setJiraSummLogs] = useState<string>("");
  const [jiraSummExternal, setJiraSummExternal] = useState<boolean>(false);
  const [jiraSummMinScore, setJiraSummMinScore] = useState<number>(0.62);
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [jiraSummary, setJiraSummary] = useState<JiraSummarizeResponse | null>(null);
  const [jiraSummError, setJiraSummError] = useState<string | null>(null);

  const apiBase = useMemo(() => getApiBase(), []);

  const canSubmit =
    form.issue_summary.trim().length > 0 &&
    form.domain.trim().length > 0 &&
    form.os.trim().length > 0 &&
    form.logs.trim().length > 0 &&
    !isSubmitting;

  const canSearch = searchQuery.trim().length > 0 && !isSearching;

  const canJiraIntake =
    jiraIntakeForm.issue_key.trim().length > 0 &&
    jiraIntakeForm.summary.trim().length > 0 &&
    !isJiraIntaking;

  const canSummarize = jiraKeyToSummarize.trim().length > 0 && !isSummarizing;

  async function readFileAsText(file: File): Promise<string> {
    return await new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onerror = () => reject(new Error("Failed to read file"));
      r.onload = () => resolve(String(r.result ?? ""));
      r.readAsText(file);
    });
  }

  async function pollDebugStatus(sessionId: string) {
    const startedAt = Date.now();
    const maxWaitMs = 20000;

    while (Date.now() - startedAt < maxWaitMs) {
      await new Promise((r) => setTimeout(r, 1000));
      try {
        const status = await getDebugStatus(sessionId);
        setResult((prev) => ({ ...(prev ?? status), ...status }));
        if (status.status && status.status !== "PROCESSING") break;
      } catch {
        // ignore transient errors while polling
      }
    }
  }

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
      setIsSubmitting(false);
      void pollDebugStatus(resp.session_id);
    } catch (err: any) {
      setError(err?.message ?? String(err));
      setIsSubmitting(false);
    }
  }

  async function onSearch(e: React.FormEvent) {
    e.preventDefault();
    setSearchError(null);
    setSearchResults([]);
    setIsSearching(true);
    try {
      const resp = await searchJira({
        query: searchQuery.trim(),
        limit: searchLimit
      });
      setSearchResults(resp.results || []);
    } catch (err: any) {
      setSearchError(err?.message ?? String(err));
    } finally {
      setIsSearching(false);
    }
  }

  async function onJiraIntake(e: React.FormEvent) {
    e.preventDefault();
    setJiraIntakeError(null);
    setJiraIntakeResult(null);
    setIsJiraIntaking(true);
    try {
      const resp = await jiraIntake({
        issue_key: jiraIntakeForm.issue_key.trim().toUpperCase(),
        summary: jiraIntakeForm.summary.trim(),
        domain: jiraIntakeForm.domain?.trim() || null,
        os: jiraIntakeForm.os?.trim() || null,
        description: jiraIntakeForm.description?.trim() || null,
        logs: jiraIntakeForm.logs?.trim() || null
      });
      setJiraIntakeResult(resp);
    } catch (err: any) {
      setJiraIntakeError(err?.message ?? String(err));
    } finally {
      setIsJiraIntaking(false);
    }
  }

  async function onJiraSummarize(e: React.FormEvent) {
    e.preventDefault();
    setJiraSummError(null);
    setJiraSummary(null);
    setIsSummarizing(true);
    try {
      const resp = await jiraSummarize({
        issue_key: jiraKeyToSummarize.trim().toUpperCase(),
        domain: jiraSummDomain.trim() || null,
        os: jiraSummOs.trim() || null,
        logs: jiraSummLogs.trim() || null,
        external_knowledge: jiraSummExternal,
        min_local_score: jiraSummMinScore
      });
      setJiraSummary(resp);
    } catch (err: any) {
      setJiraSummError(err?.message ?? String(err));
    } finally {
      setIsSummarizing(false);
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
          <div className="cardTitle">Add new JIRA (offline intake)</div>
          <div className="muted">
            Stores the issue into <code>jira_issues</code>/<code>jira_embeddings</code> so you can
            search/summarize it later.
          </div>

          <form onSubmit={onJiraIntake} className="form">
            <div className="row">
              <div className="field">
                <label className="label" htmlFor="intakeKey">
                  JIRA key
                </label>
                <input
                  id="intakeKey"
                  className="input"
                  placeholder="e.g. SYSCROS-123456"
                  value={jiraIntakeForm.issue_key}
                  onChange={(e) =>
                    setJiraIntakeForm((s) => ({ ...s, issue_key: e.target.value.toUpperCase() }))
                  }
                />
              </div>

              <div className="field">
                <label className="label" htmlFor="intakeOs">
                  OS
                </label>
                <select
                  id="intakeOs"
                  className="select"
                  value={jiraIntakeForm.os ?? detectOs()}
                  onChange={(e) => setJiraIntakeForm((s) => ({ ...s, os: e.target.value }))}
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
              <label className="label" htmlFor="intakeSummary">
                Summary
              </label>
              <input
                id="intakeSummary"
                className="input"
                placeholder="e.g. Video flicker during playback"
                value={jiraIntakeForm.summary}
                onChange={(e) => setJiraIntakeForm((s) => ({ ...s, summary: e.target.value }))}
              />
            </div>

            <div className="row">
              <div className="field">
                <label className="label" htmlFor="intakeDomain">
                  Domain
                </label>
                <input
                  id="intakeDomain"
                  className="input"
                  placeholder="e.g. media"
                  value={jiraIntakeForm.domain ?? ""}
                  onChange={(e) => setJiraIntakeForm((s) => ({ ...s, domain: e.target.value }))}
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="intakeLogsFile">
                  Logs file (optional)
                </label>
                <input
                  id="intakeLogsFile"
                  className="input"
                  type="file"
                  accept=".txt,.log"
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    const text = await readFileAsText(f);
                    setJiraIntakeForm((s) => ({ ...s, logs: text }));
                  }}
                />
              </div>
            </div>

            <div className="field">
              <label className="label" htmlFor="intakeLogs">
                Logs (optional)
              </label>
              <textarea
                id="intakeLogs"
                className="textarea"
                placeholder="Paste relevant logs here (optional)…"
                value={jiraIntakeForm.logs ?? ""}
                onChange={(e) => setJiraIntakeForm((s) => ({ ...s, logs: e.target.value }))}
                rows={6}
              />
            </div>

            <div className="actions">
              <button className="button" disabled={!canJiraIntake} type="submit">
                {isJiraIntaking ? "Saving…" : "Save JIRA to DB"}
              </button>
              <button
                className="buttonSecondary"
                type="button"
                onClick={() => {
                  setJiraIntakeForm({
                    issue_key: "",
                    summary: "",
                    domain: "",
                    os: detectOs(),
                    logs: ""
                  });
                  setJiraIntakeResult(null);
                  setJiraIntakeError(null);
                }}
                disabled={isJiraIntaking}
              >
                Clear
              </button>
            </div>
          </form>

          {jiraIntakeError && (
            <div className="errorBox">
              <div className="errorTitle">Intake failed</div>
              <pre className="pre">{jiraIntakeError}</pre>
            </div>
          )}
          {jiraIntakeResult && (
            <div className="resultBox">
              <div className="kv">
                <div className="k">issue_key</div>
                <div className="v">
                  <code>{jiraIntakeResult.issue_key}</code>
                </div>
              </div>
              <div className="kv">
                <div className="k">embedded</div>
                <div className="v">
                  <code>{String(Boolean(jiraIntakeResult.embedded))}</code>
                </div>
              </div>
            </div>
          )}
        </section>

        <section className="card">
          <div className="cardTitle">Fetch &amp; summarize JIRA</div>
          <div className="muted">
            Runs the swarm summary on your locally stored <code>jira_issues</code> and returns{" "}
            <code>report + analysis</code>.
          </div>

          <form onSubmit={onJiraSummarize} className="form">
            <div className="row">
              <div className="field">
                <label className="label" htmlFor="summKey">
                  JIRA key
                </label>
                <input
                  id="summKey"
                  className="input"
                  placeholder="e.g. SYSCROS-123456"
                  value={jiraKeyToSummarize}
                  onChange={(e) => setJiraKeyToSummarize(e.target.value.toUpperCase())}
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="summDomain">
                  Domain
                </label>
                <input
                  id="summDomain"
                  className="input"
                  placeholder="e.g. media"
                  value={jiraSummDomain}
                  onChange={(e) => setJiraSummDomain(e.target.value)}
                />
              </div>
            </div>

            <div className="row">
              <div className="field">
                <label className="label" htmlFor="summOs">
                  OS
                </label>
                <select
                  id="summOs"
                  className="select"
                  value={jiraSummOs}
                  onChange={(e) => setJiraSummOs(e.target.value)}
                >
                  {OS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label className="label" htmlFor="summLogsFile">
                  Logs file (optional)
                </label>
                <input
                  id="summLogsFile"
                  className="input"
                  type="file"
                  accept=".txt,.log"
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    const text = await readFileAsText(f);
                    setJiraSummLogs(text);
                  }}
                />
              </div>
            </div>

            <div className="field">
              <label className="label" htmlFor="summLogs">
                Logs (optional)
              </label>
              <textarea
                id="summLogs"
                className="textarea"
                placeholder="Paste relevant logs (optional)…"
                value={jiraSummLogs}
                onChange={(e) => setJiraSummLogs(e.target.value)}
                rows={6}
              />
            </div>

            <div className="row">
              <div className="field">
                <label className="label" htmlFor="summExternal">
                  External knowledge
                </label>
                <select
                  id="summExternal"
                  className="select"
                  value={jiraSummExternal ? "yes" : "no"}
                  onChange={(e) => setJiraSummExternal(e.target.value === "yes")}
                >
                  <option value="no">No</option>
                  <option value="yes">Yes (if similarity &lt; threshold)</option>
                </select>
              </div>
              <div className="field">
                <label className="label" htmlFor="summMinScore">
                  Similarity threshold
                </label>
                <input
                  id="summMinScore"
                  className="input"
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={jiraSummMinScore}
                  onChange={(e) => setJiraSummMinScore(Number(e.target.value || 0.62))}
                />
              </div>
            </div>

            <div className="actions">
              <button className="button" disabled={!canSummarize} type="submit">
                {isSummarizing ? "Summarizing…" : "Fetch & summarize"}
              </button>
              <button
                className="buttonSecondary"
                type="button"
                onClick={() => {
                  setJiraSummary(null);
                  setJiraSummError(null);
                }}
                disabled={isSummarizing}
              >
                Clear output
              </button>
            </div>
          </form>

          {jiraSummError && (
            <div className="errorBox">
              <div className="errorTitle">Summarize failed</div>
              <pre className="pre">{jiraSummError}</pre>
            </div>
          )}

          {jiraSummary && (
            <div className="resultBox">
              <div className="kv">
                <div className="k">issue_key</div>
                <div className="v">
                  <code>{jiraSummary.issue_key}</code>
                </div>
              </div>
              <div className="hint">Report</div>
              <pre className="pre">{jiraSummary.report}</pre>
              <div className="hint">Analysis</div>
              <pre className="pre">{jiraSummary.analysis}</pre>
            </div>
          )}
        </section>

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
                  setForm({ issue_summary: "", domain: "", os: detectOs(), logs: "" });
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
                <div className="k">os</div>
                <div className="v">
                  <code>{result.os ?? form.os}</code>
                </div>
              </div>
              <div className="kv">
                <div className="k">domain</div>
                <div className="v">
                  <code>{result.domain ?? form.domain}</code>
                </div>
              </div>
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
              {"has_embedding" in result ? (
                <div className="kv">
                  <div className="k">has_embedding</div>
                  <div className="v">
                    <code>{String(Boolean(result.has_embedding))}</code>
                  </div>
                </div>
              ) : null}
              <div className="hint">
                The backend runs embedding generation asynchronously. You can check DB tables
                (<code>debug_sessions</code>, <code>debug_embeddings</code>) to see progress.
              </div>
            </div>
          )}
        </section>

        <section className="card">
          <div className="cardTitle">JIRA Similarity Search</div>

          <form onSubmit={onSearch} className="form">
            <div className="field">
              <label className="label" htmlFor="searchQuery">
                Query
              </label>
              <input
                id="searchQuery"
                className="input"
                placeholder="e.g. video flicker after resume, i915, DRM overlay…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            <div className="row">
              <div className="field">
                <label className="label" htmlFor="searchLimit">
                  Top K
                </label>
                <input
                  id="searchLimit"
                  className="input"
                  type="number"
                  min={1}
                  max={20}
                  value={searchLimit}
                  onChange={(e) => setSearchLimit(Number(e.target.value || 5))}
                />
              </div>
              <div className="field">
                <label className="label">&nbsp;</label>
                <button className="button" disabled={!canSearch} type="submit">
                  {isSearching ? "Searching…" : "Search JIRA"}
                </button>
              </div>
            </div>
          </form>

          {searchError && (
            <div className="errorBox">
              <div className="errorTitle">Search failed</div>
              <pre className="pre">{searchError}</pre>
            </div>
          )}

          {!searchError && searchResults.length === 0 && (
            <div className="muted">
              Enter a query and click <b>Search JIRA</b>. Results come from your local Postgres
              tables (<code>jira_issues</code>, <code>jira_embeddings</code>).
            </div>
          )}

          {searchResults.length > 0 && (
            <div className="resultBox">
              {searchResults.map((r) => (
                <div className="kv" key={r.issue_key}>
                  <div className="k">{r.issue_key}</div>
                  <div className="v">
                    <div>
                      <b>{(r.similarity ?? 0).toFixed(3)}</b>{" "}
                      {r.url ? (
                        <a href={r.url} target="_blank" rel="noreferrer">
                          open
                        </a>
                      ) : null}
                    </div>
                    <div className="muted">{r.summary}</div>
                    {r.latest_comment ? (
                      <div className="hint">
                        <b>Latest comment:</b> {r.latest_comment}
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
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

