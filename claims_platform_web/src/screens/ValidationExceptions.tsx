import { useEffect, useState } from "react";
import { api, download } from "../api";
import { Decision, Figure, Message, Panel, RunStatus, Severity, Status, useAction, useLoad } from "../components/ui";
import { STATUS_LABEL, canAnalyse, canApprove, dateTime, isInternal, n, seconds } from "../format";
import type { ExceptionEvent, ExceptionInfo, Explanation, RunSummary, Submission, User } from "../types";
import type { ClientScreenProps } from "./props";

const ACTIVE = ["queued", "running"];

export async function waitForRun(id: number): Promise<RunSummary> {
  for (let i = 0; i < 600; i++) {
    const run = await api<RunSummary>(`/api/runs/${id}`);
    if (!ACTIVE.includes(run.status)) return run;
    await new Promise((r) => setTimeout(r, 1000));
  }
  return api<RunSummary>(`/api/runs/${id}`);
}

export function ValidationExceptions({ client, user, refresh, stamp }: ClientScreenProps) {
  const subs = useLoad(() => api<Submission[]>(`/api/clients/${client.id}/submissions`), [client.id, stamp]);
  const latest = subs.data?.[0];
  const run = latest?.run ?? null;
  const [filter, setFilter] = useState<"open" | "all">("open");
  const excs = useLoad(() => api<ExceptionInfo[]>(`/api/clients/${client.id}/exceptions${filter === "open" ? "?status=open" : ""}`),
    [client.id, filter, stamp]);
  const [selected, setSelected] = useState<number | null>(null);
  const after = async () => { await subs.reload(); await refresh(); };
  const { act, busy, error, done } = useAction(after);

  async function start(path: string) {
    await act(async () => {
      const r = await api<RunSummary>(path, { method: "POST" });
      const finished = await waitForRun(r.id);
      if (finished.status === "failed") throw new Error(`The run failed: ${finished.error}. Retry when the cause is fixed.`);
      return finished;
    });
  }

  return (
    <div className="stack">
      <Panel title={latest ? `File #${latest.sequence}: ${latest.filename}` : "Latest validation"}
        intro={run ? <>Run {run.id}, attempt {run.attempts}, finished {dateTime(run.finished_at)} in {seconds(run.duration_ms)}.</> : "Every row is checked by code against the approved rules. AI is never used for these checks."}
        actions={<>
          {latest && canAnalyse(user.role) && (!run || run.status === "completed") && (
            <button className="btn primary" disabled={busy} onClick={() => start(`/api/submissions/${latest.id}/runs`)}>
              {busy ? "Validating…" : run ? "Validate again" : `Validate file #${latest.sequence}`}
            </button>
          )}
          {run && ["failed", "interrupted"].includes(run.status) && canAnalyse(user.role) && (
            <button className="btn primary" disabled={busy} onClick={() => start(`/api/runs/${run.id}/retry`)}>Retry run</button>
          )}
          {run?.status === "completed" && (
            <button className="btn" onClick={() => download(`/api/runs/${run.id}/findings.csv`, `${client.code}-file-${latest?.sequence}-findings.csv`)}>
              Download findings
            </button>
          )}
        </>}>
        {!latest ? (
          <div className="empty">No file yet. Upload the client's claims extract.</div>
        ) : !run ? (
          <div className="empty">This file has not been validated. {canAnalyse(user.role) ? "An approved mapping is needed first." : "The implementation team will validate it."}</div>
        ) : (
          <div className="stack" style={{ gap: "0.75rem" }}>
            <div className="row"><RunStatus value={run.status} />{run.status === "completed" && <Decision value={run.decision} />}
              {run.scan_complete === false && <span className="chip blocker">File not read to the end</span>}</div>
            {run.error && <p className="message error">{run.error}</p>}
            {run.status === "completed" && (
              <div className="figures">
                <Figure value={n(run.rows_checked)} what="Rows checked" />
                <Figure value={n(run.blockers)} what="Blocker findings" tone={run.blockers ? "blocker" : "pass"} />
                <Figure value={n(run.warnings)} what="Warning findings" tone={run.warnings ? "warning" : undefined} />
              </div>
            )}
          </div>
        )}
        <div style={{ marginTop: "0.75rem" }}><Message error={error} done={done} /></div>
      </Panel>

      <Panel title="Exceptions"
        intro="One exception per broken rule, tracked across files. They close when a resubmitted file no longer contains them; blockers cannot be waived."
        actions={<div className="row" role="group" aria-label="Show">
          <button className={`btn small${filter === "open" ? " primary" : ""}`} onClick={() => setFilter("open")}>Open</button>
          <button className={`btn small${filter === "all" ? " primary" : ""}`} onClick={() => setFilter("all")}>All</button>
        </div>}>
        <Message error={excs.error} />
        {excs.data && excs.data.length === 0 ? (
          <div className="empty">{filter === "open" ? "No open exceptions." : "No exceptions recorded yet."}</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Severity</th><th>Client column</th><th>Rule broken</th><th className="right">Rows</th><th>Status</th><th>Owner</th><th>Files</th></tr></thead>
              <tbody>
                {(excs.data ?? []).map((e) => (
                  <tr key={e.id} className={`clickable${selected === e.id ? " selected" : ""}`} onClick={() => setSelected(e.id)}>
                    <td><Severity value={e.severity} /></td>
                    <td><button className="btn link" onClick={(ev) => { ev.stopPropagation(); setSelected(e.id); }}>{e.client_column || e.field}</button><div className="faint">{e.field}</div></td>
                    <td>{e.rule}</td>
                    <td className="right">{n(e.current_count)}</td>
                    <td><Status value={e.status} /></td>
                    <td>{e.owner ?? <span className="faint">Unassigned</span>}</td>
                    <td className="small">#{e.first_submission}{e.last_submission !== e.first_submission && ` to #${e.last_submission}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {run?.status === "completed" && <Findings runId={run.id} />}

      {selected !== null && (
        <ExceptionDrawer id={selected} clientId={client.id} user={user} onClose={() => setSelected(null)}
          onChanged={async () => { await excs.reload(); await refresh(); }} />
      )}
    </div>
  );
}

interface FindingPage { total: number; stored: number; counted: number; items: { line: number; field: string; client_column: string; entered: string; rule: string; severity: string; message: string }[] }

function Findings({ runId }: { runId: number }) {
  const [offset, setOffset] = useState(0);
  const [severity, setSeverity] = useState("");
  const page = useLoad(() => api<FindingPage>(`/api/runs/${runId}/findings?limit=25&offset=${offset}${severity ? `&severity=${severity}` : ""}`), [runId, offset, severity]);
  const d = page.data;
  return (
    <Panel title="Row-level findings" intro={d ? `${n(d.counted)} findings counted${d.stored < d.counted ? `; the first ${n(d.stored)} are kept with their values` : ""}.` : undefined}
      actions={<select value={severity} onChange={(e) => { setOffset(0); setSeverity(e.target.value); }} aria-label="Severity" style={{ width: "auto" }}>
        <option value="">Blockers and warnings</option><option value="blocker">Blockers</option><option value="warning">Warnings</option>
      </select>}>
      {d && d.items.length === 0 ? <div className="empty">No findings. Every row passed every rule.</div> : (
        <div className="table-wrap">
          <table>
            <thead><tr><th className="right">Line</th><th>Client column</th><th>Value sent</th><th>Problem</th><th>Severity</th></tr></thead>
            <tbody>
              {(d?.items ?? []).map((f, i) => (
                <tr key={`${f.line}-${f.field}-${i}`}>
                  <td className="right">{f.line}</td>
                  <td>{f.client_column}</td>
                  <td>{f.entered === "" ? <span className="faint">(blank)</span> : f.entered}</td>
                  <td>{f.message}<div className="faint">{f.rule}</div></td>
                  <td><Severity value={f.severity} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {d && d.total > 25 && (
        <div className="row" style={{ marginTop: "0.75rem" }}>
          <button className="btn small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous</button>
          <span className="small muted">{offset + 1} to {Math.min(offset + 25, d.total)} of {n(d.total)}</span>
          <button className="btn small" disabled={offset + 25 >= d.total} onClick={() => setOffset(offset + 25)}>Next</button>
        </div>
      )}
    </Panel>
  );
}

function describe(ev: ExceptionEvent): string {
  const d = ev.detail as Record<string, unknown>;
  switch (ev.kind) {
    case "created": return `Opened from file #${d.submission} with ${d.count} rows.`;
    case "auto_resolved": return `Resolved: not found in file #${d.submission}.`;
    case "reopened": return `Reopened in file #${d.submission} (${d.count} rows). ${d.reason ?? ""}`;
    case "still_open": return `Still present in file #${d.submission}: ${d.before} to ${d.after} rows.`;
    case "note": return `Note: ${d.note}`;
    default: {
      const parts: string[] = [];
      if (Array.isArray(d.status)) parts.push(`status ${d.status[0]} to ${d.status[1]}`);
      if (Array.isArray(d.owner)) parts.push("owner changed");
      if (d.note) parts.push(`note: ${d.note}`);
      return parts.length ? `Updated: ${parts.join("; ")}.` : "Updated.";
    }
  }
}

function ExceptionDrawer({ id, clientId, user, onClose, onChanged }: { id: number; clientId: number; user: User; onClose: () => void; onChanged: () => Promise<void> }) {
  const detail = useLoad(() => api<ExceptionInfo & { events: ExceptionEvent[] }>(`/api/exceptions/${id}`), [id]);
  const expl = useLoad(() => api<Explanation>(`/api/exceptions/${id}/explanation`), [id]);
  const team = useLoad(() => (isInternal(user.role) ? api<User[]>(`/api/clients/${clientId}/team`) : Promise.resolve([] as User[])), [clientId]);
  const [ai, setAi] = useState<Explanation | null>(null);
  const [status, setStatus] = useState("");
  const [owner, setOwner] = useState("");
  const [note, setNote] = useState("");
  const after = async () => { await detail.reload(); await onChanged(); setNote(""); };
  const { act, busy, error, done } = useAction(after);
  const aiAction = useAction();
  const e = detail.data;
  useEffect(() => {
    if (e) { setStatus(e.status); setOwner(e.owner_id ? String(e.owner_id) : ""); }
  }, [e]);
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => ev.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  if (!e) return null;
  const statuses = ["open", "in_progress", ...(e.severity === "warning" && canApprove(user.role) ? ["accepted"] : [])];
  const editable = isInternal(user.role) && e.status !== "resolved";

  function save() {
    const body: Record<string, unknown> = { note };
    if (editable && status !== e!.status) body.status = status;
    if (editable && owner && Number(owner) !== e!.owner_id) body.owner_id = Number(owner);
    if (editable && !owner && e!.owner_id) body.clear_owner = true;
    return act(() => api(`/api/exceptions/${id}`, { method: "PATCH", json: body }), "Saved.");
  }

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="exc-title">
        <div className="row between">
          <div className="row"><Severity value={e.severity} /><Status value={e.status} /></div>
          <button className="btn small" onClick={onClose} autoFocus>Close</button>
        </div>
        <div>
          <h2 id="exc-title">{e.client_column || e.field}: {e.rule}</h2>
          <p className="muted small">{n(e.current_count)} rows in the latest file. First seen in file #{e.first_submission} with {n(e.first_count)} rows.</p>
          {e.resolution && <p className="small" style={{ marginTop: "0.4rem" }}>{e.resolution}</p>}
        </div>
        {expl.data && (
          <div className="stack" style={{ gap: "0.5rem" }}>
            <h3>What it means</h3>
            <p className="small">{expl.data.summary}</p>
            <p className="small"><strong>Why it matters.</strong> {expl.data.why_it_matters}</p>
            <p className="small"><strong>How the client fixes it.</strong> {expl.data.how_to_fix}</p>
            {ai?.ai_text && <p className="message info">Reworded by Gemini, and checked to add no figures: {ai.ai_text}</p>}
            {ai?.ai_error && <p className="message info">{ai.ai_error}</p>}
            {!ai && isInternal(user.role) && (
              <button className="btn small" style={{ justifySelf: "start" }} disabled={aiAction.busy}
                onClick={async () => setAi((await aiAction.act(() => api<Explanation>(`/api/exceptions/${id}/explanation?ai=true`))) ?? null)}>
                {aiAction.busy ? "Asking Gemini…" : "Reword for the client with Gemini"}
              </button>
            )}
            {isInternal(user.role) && <p className="faint">Gemini receives the rule, column heading and row count only, never values.</p>}
          </div>
        )}
        <div className="stack" style={{ gap: "0.6rem" }}>
          <h3>{editable ? "Update" : "Add a note"}</h3>
          {editable && (
            <div className="grid-2" style={{ gap: "0.6rem" }}>
              <label className="field">Status
                <select value={status} onChange={(ev) => setStatus(ev.target.value)}>
                  {[...new Set([e.status, ...statuses])].map((s) => <option key={s} value={s}>{STATUS_LABEL[s] ?? s}</option>)}
                </select>
              </label>
              <label className="field">Owner
                <select value={owner} onChange={(ev) => setOwner(ev.target.value)}>
                  <option value="">Unassigned</option>
                  {(team.data ?? []).map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
                </select>
              </label>
            </div>
          )}
          <label className="field">Note
            <textarea value={note} onChange={(ev) => setNote(ev.target.value)} style={{ minHeight: "4.5rem" }}
              placeholder={status === "accepted" ? "Why this warning is acceptable (required)" : "Optional"} />
          </label>
          <div className="row"><button className="btn primary" disabled={busy} onClick={save}>Save</button></div>
          {e.severity === "blocker" && editable && <p className="faint">Blockers close only when a corrected file no longer contains them.</p>}
          <Message error={error} done={done} />
        </div>
        <div className="stack" style={{ gap: "0.5rem" }}>
          <h3>History</h3>
          <ol className="events">
            {e.events.map((ev, i) => (
              <li key={i}><span className="faint">{dateTime(ev.at)}, {ev.actor}</span><div>{describe(ev)}</div></li>
            ))}
          </ol>
        </div>
      </aside>
    </>
  );
}
