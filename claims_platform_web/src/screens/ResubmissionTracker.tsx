import { useState } from "react";
import { api } from "../api";
import { Decision, Message, Panel, RunStatus, useAction, useLoad } from "../components/ui";
import { canAnalyse, dateTime, isInternal, n, plural } from "../format";
import type { Communication, GroupChange, HistoryItem } from "../types";
import type { ClientScreenProps } from "./props";

function Group({ title, tone, items }: { title: string; tone: "pass" | "blocker" | "warning"; items: GroupChange[] }) {
  return (
    <div>
      <span className={`chip ${tone}`}>{title}: {items.length}</span>
      {items.length > 0 && (
        <ul>
          {items.map((g) => (
            <li key={`${g.field}-${g.rule}`}>
              {g.field}: {g.rule} <span className="faint">({n(g.before)} to {n(g.after)} rows)</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ResubmissionTracker({ client, user, stamp }: ClientScreenProps) {
  const history = useLoad(() => api<HistoryItem[]>(`/api/clients/${client.id}/resubmissions`), [client.id, stamp]);
  const rounds = history.data ?? [];
  const validated = rounds.filter((r) => r.run?.status === "completed");
  const max = Math.max(1, ...validated.map((r) => r.run?.blockers ?? 0));
  return (
    <div className="stack">
      <Panel title="Blockers per file" intro="The client is ready only once a file has none.">
        {validated.length === 0 ? <div className="empty">No validated files yet.</div> : (
          <div className="bars">
            {validated.map((r) => (
              <div className="barrow" key={r.submission_id}>
                <span>File #{r.sequence}</span>
                <div className={`fill${r.run?.blockers ? "" : " zero"}`} style={{ width: `${Math.max(2, ((r.run?.blockers ?? 0) / max) * 100)}%` }} />
                <span className="num">{n(r.run?.blockers)}</span>
              </div>
            ))}
          </div>
        )}
      </Panel>
      <Panel title="Files in order" intro="Each resubmission is compared with the one before it, rule by rule rather than line by line.">
        {rounds.length === 0 ? <div className="empty">No files yet.</div> : (
          <ol className="rounds">
            {rounds.map((r) => (
              <li key={r.submission_id} className="round">
                <div className={`seq${r.run?.decision === "Ready" ? " ready" : ""}`} aria-label={`File ${r.sequence}`}>{r.sequence}</div>
                <div>
                  <div className="row">
                    <strong>{r.filename}</strong>
                    {r.run?.status === "completed" ? <Decision value={r.run.decision} /> : <RunStatus value={r.run?.status} />}
                  </div>
                  <p className="faint">
                    Received {dateTime(r.uploaded_at)}.{r.run?.status === "completed" && ` ${plural(r.run.rows_checked, "row")}, ${plural(r.run.blockers, "blocker")}, ${plural(r.run.warnings, "warning")}.`}
                  </p>
                  {r.comparison && (
                    <>
                      {r.comparison.mapping_changed && <p className="faint">The column mapping changed since the previous file, so some differences may come from the mapping.</p>}
                      <div className="groups">
                        <Group title="Fixed" tone="pass" items={r.comparison.fixed} />
                        <Group title="Still open" tone="warning" items={r.comparison.unresolved} />
                        <Group title="New" tone="blocker" items={r.comparison.new} />
                      </div>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </Panel>
      <Communications clientId={client.id} canDraft={canAnalyse(user.role)} canSend={isInternal(user.role)} validatedFiles={validated.length} stamp={stamp} />
    </div>
  );
}

function Communications({ clientId, canDraft, canSend, validatedFiles, stamp }: { clientId: number; canDraft: boolean; canSend: boolean; validatedFiles: number; stamp: string }) {
  const list = useLoad(() => api<Communication[]>(`/api/clients/${clientId}/communications`), [clientId, stamp]);
  const [open, setOpen] = useState<Communication | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const { act, busy, error, done } = useAction(list.reload);
  async function show(id: number) {
    setOpen(await api<Communication>(`/api/communications/${id}`));
  }
  async function draft(kind: string) {
    const c = await act(() => api<Communication>(`/api/clients/${clientId}/communications`, { json: { kind, subject, body } }), "Draft written. Read it, then release it to the client.");
    if (c) { setOpen(c); setSubject(""); setBody(""); }
  }
  return (
    <Panel title="Client communication"
      intro={canSend ? "Letters are written by code from the verified findings, using the client's own column names. The client sees a letter only after it is released." : "Letters from the implementation team about your files."}>
      {canDraft && (
        <div className="row" style={{ marginBottom: "1rem" }}>
          <button className="btn" disabled={busy || validatedFiles === 0} onClick={() => draft("issue_letter")}>Write issue letter for the latest file</button>
          <button className="btn" disabled={busy || validatedFiles < 2} onClick={() => draft("resubmission_summary")}>Write resubmission summary</button>
        </div>
      )}
      {(list.data ?? []).length === 0 ? <div className="empty">No messages yet.</div> : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Subject</th><th>Status</th><th>Written</th><th>Released</th></tr></thead>
            <tbody>
              {(list.data ?? []).map((c) => (
                <tr key={c.id} className={`clickable${open?.id === c.id ? " selected" : ""}`} onClick={() => show(c.id)}>
                  <td><button className="btn link" onClick={(e) => { e.stopPropagation(); void show(c.id); }}>{c.subject}</button></td>
                  <td><span className={`chip ${c.status === "sent" ? "pass" : "neutral"}`}>{c.status === "sent" ? "Released" : "Draft"}</span></td>
                  <td className="small">{dateTime(c.created_at)}{c.created_by && `, ${c.created_by}`}</td>
                  <td className="small">{c.sent_at ? `${dateTime(c.sent_at)}, ${c.sent_by}` : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open && (
        <div className="stack" style={{ marginTop: "1rem", gap: "0.6rem" }}>
          <div className="row between">
            <h3>{open.subject}</h3>
            <div className="row">
              {open.status === "draft" && canSend && (
                <button className="btn primary" disabled={busy}
                  onClick={async () => { await act(() => api(`/api/communications/${open.id}/send`, { method: "POST" }), "Released to the client contact."); setOpen({ ...open, status: "sent" }); }}>
                  Release to client
                </button>
              )}
              <button className="btn small" onClick={() => setOpen(null)}>Close</button>
            </div>
          </div>
          <div className="letter">{open.body}</div>
        </div>
      )}
      {canDraft && (
        <details style={{ marginTop: "1rem" }}>
          <summary className="small">Write a note instead</summary>
          <div className="stack" style={{ gap: "0.6rem", marginTop: "0.6rem" }}>
            <label className="field">Subject<input type="text" value={subject} onChange={(e) => setSubject(e.target.value)} /></label>
            <label className="field">Message<textarea value={body} onChange={(e) => setBody(e.target.value)} /></label>
            <div className="row"><button className="btn" disabled={busy} onClick={() => draft("note")}>Save note as draft</button></div>
          </div>
        </details>
      )}
      <div style={{ marginTop: "0.75rem" }}><Message error={error} done={done} /></div>
      <p className="faint" style={{ marginTop: "0.5rem" }}>In this pilot, releasing makes the letter visible to the client contact inside the platform. No e-mail is sent.</p>
    </Panel>
  );
}
