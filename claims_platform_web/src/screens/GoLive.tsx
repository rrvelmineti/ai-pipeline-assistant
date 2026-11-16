import { useState } from "react";
import { api, download } from "../api";
import { Checklist, Figure, Message, Panel, useAction, useLoad } from "../components/ui";
import { canAnalyse, canApprove, date, dateTime, n, pct, seconds } from "../format";
import type { AuditRow, ExportInfo, Milestone, Scorecard } from "../types";
import type { ClientScreenProps } from "./props";

async function waitForExport(clientId: number): Promise<ExportInfo | undefined> {
  for (let i = 0; i < 900; i++) {
    const [latest] = await api<ExportInfo[]>(`/api/clients/${clientId}/exports`);
    if (!latest || !["pending", "in_progress"].includes(latest.status)) return latest;
    await new Promise((r) => setTimeout(r, 1000));
  }
  return undefined;
}

export function GoLive({ client, user, refresh, stamp }: ClientScreenProps) {
  const r = client.readiness;
  const card = useLoad(() => api<Scorecard>(`/api/clients/${client.id}/scorecard`), [client.id, stamp]);
  const [comment, setComment] = useState("");
  const { act, busy, error, done } = useAction(refresh);
  const exp = r.export;
  const approved = r.approval?.decision === "approved";

  return (
    <div className="stack">
      <div className="grid-2">
        <Panel title="Go-live readiness" intro="Every check must pass before anyone can approve. Open blockers always stop approval.">
          <Checklist checks={r.checks} />
        </Panel>
        <Panel title="Approval"
          intro={r.run ? `For file #${r.latest_submission}, run ${r.run.id}: ${n(r.run.rows_checked)} rows, ${n(r.run.blockers)} blockers, ${n(r.run.warnings)} warnings.` : "No validated file yet."}>
          {r.approval && (
            <p className={`message ${approved ? "ok" : "error"}`}>
              {approved ? "Go-live approved" : "Go-live rejected"} on {dateTime(r.approval.at)}. {r.approval.comment}
            </p>
          )}
          {canApprove(user.role) && r.run && !approved ? (
            <div className="stack" style={{ gap: "0.75rem", marginTop: "0.75rem" }}>
              <label className="field">Approval comment
                <textarea value={comment} onChange={(e) => setComment(e.target.value)} style={{ minHeight: "4.5rem" }}
                  placeholder="What you checked. Required when rejecting." />
              </label>
              <div className="row">
                <button className="btn primary" disabled={busy || !r.ready_for_approval}
                  onClick={() => act(() => api(`/api/clients/${client.id}/golive`, { json: { approve: true, comment } }), "Go-live approved and recorded.")}>
                  Approve go-live
                </button>
                <button className="btn danger" disabled={busy}
                  onClick={() => act(() => api(`/api/clients/${client.id}/golive`, { json: { approve: false, comment } }), "Rejection recorded.")}>
                  Reject
                </button>
              </div>
              {!r.ready_for_approval && <p className="faint">Approval opens once every readiness check passes.</p>}
              <p className="faint">You cannot approve a file whose mapping you prepared or whose validation you ran.</p>
            </div>
          ) : !canApprove(user.role) && !approved ? (
            <p className="muted small" style={{ marginTop: "0.5rem" }}>An approver signs off go-live.</p>
          ) : null}
          <Message error={error} done={done} />
        </Panel>
      </div>

      <ExportPanel clientId={client.id} exp={exp} approved={approved} canRun={canAnalyse(user.role)} onDone={refresh} />

      <Panel title="Go-live evidence"
        intro="One ZIP with the readiness report, findings, approved rules and mapping, exceptions and their history, resubmissions, approvals, exports and the audit trail, plus a SHA-256 manifest."
        actions={<button className="btn" disabled={!r.run} onClick={() => download(`/api/clients/${client.id}/evidence`, `${client.code}-go-live-evidence.zip`)}>Download evidence package</button>}>
        <p className="faint">Generating the package is itself recorded in the audit trail.</p>
      </Panel>

      {card.data && <ScorecardPanel card={card.data} />}
      <Timeline milestones={client.milestones} canEdit={canAnalyse(user.role)} onDone={refresh} target={client.go_live_target} />
      <Audit clientId={client.id} stamp={stamp} />
    </div>
  );
}

function ExportPanel({ clientId, exp, approved, canRun, onDone }: { clientId: number; exp: ExportInfo | null; approved: boolean; canRun: boolean; onDone: () => void }) {
  const { act, busy, error, done } = useAction(onDone);
  async function run(path: string) {
    await act(async () => {
      await api(path, { method: "POST" });
      const out = await waitForExport(clientId);
      if (out?.status === "failed") throw new Error(out.last_error ?? "The export failed. Retry to resume.");
      return out;
    }, "Export finished.");
  }
  return (
    <Panel title="Export to the claims system"
      intro="Approved claims are sent in batches. Each batch has a fixed key, so a retry never loads a claim twice."
      actions={canRun && <>
        {approved && !exp && <button className="btn primary" disabled={busy} onClick={() => run(`/api/clients/${clientId}/exports`)}>{busy ? "Exporting…" : "Start export"}</button>}
        {exp?.status === "failed" && <button className="btn primary" disabled={busy} onClick={() => run(`/api/exports/${exp.id}/retry`)}>{busy ? "Resuming…" : `Resume from batch ${exp.batches_done + 1}`}</button>}
      </>}>
      {!exp ? (
        <div className="empty">{approved ? "Approved and ready to export." : "Export opens after go-live approval."}</div>
      ) : (
        <div className="stack" style={{ gap: "0.75rem" }}>
          <div className="figures">
            <Figure value={exp.status === "completed" ? "Completed" : exp.status === "failed" ? "Failed" : "Running"} what="Status" tone={exp.status === "completed" ? "pass" : exp.status === "failed" ? "blocker" : undefined} />
            <Figure value={`${exp.batches_done} of ${exp.batches_total}`} what="Batches delivered" />
            <Figure value={n(exp.sent_records)} what="Claims loaded" />
            <Figure value={n(exp.skipped_duplicates)} what="Duplicates refused" />
            <Figure value={n(exp.batch_retries)} what="Batch retries" />
            <Figure value={seconds(exp.duration_ms)} what="Time" />
          </div>
          {exp.last_error && <p className="message error">{exp.last_error}</p>}
        </div>
      )}
      <div style={{ marginTop: "0.75rem" }}><Message error={error} done={done} /></div>
    </Panel>
  );
}

function ScorecardPanel({ card }: { card: Scorecard }) {
  return (
    <Panel title="Client scorecard" intro="From this client's records only. No figure here is estimated.">
      <div className="figures">
        <Figure value={card.rounds_to_acceptance ?? "Not yet"} what="Files until accepted" />
        <Figure value={card.first_pass_acceptance === null ? "–" : card.first_pass_acceptance ? "Yes" : "No"} what="First file accepted" />
        <Figure value={pct(card.rework_rate)} what="Files sent back" />
        <Figure value={`${card.exceptions.resolved} of ${card.exceptions.total}`} what="Exceptions resolved" />
        <Figure value={card.exceptions.median_hours_to_resolve === null ? "–" : `${card.exceptions.median_hours_to_resolve} h`} what="Median time to resolve" />
        <Figure value={card.exceptions.reopened_ever} what="Exceptions that came back" tone={card.exceptions.reopened_ever ? "warning" : undefined} />
        <Figure value={card.days_in_onboarding} what="Days in onboarding" />
        <Figure value={`${card.milestones_done} of ${card.milestones_total}`} what="Milestones done" />
      </div>
    </Panel>
  );
}

const MILESTONE_STATUS = ["not_started", "in_progress", "done", "blocked"];

function Timeline({ milestones, canEdit, onDone, target }: { milestones: Milestone[]; canEdit: boolean; onDone: () => void; target: string | null }) {
  const { act, error } = useAction(onDone);
  const patch = (id: number, json: Record<string, unknown>) => act(() => api(`/api/milestones/${id}`, { method: "PATCH", json }));
  return (
    <Panel title="Implementation timeline" intro={`Target go-live ${date(target)}. Steps complete themselves as the work happens; dates are set by the team.`}>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Step</th><th>Status</th><th>Due</th><th>Completed</th></tr></thead>
          <tbody>
            {milestones.map((m, i) => (
              <tr key={m.id}>
                <td><span className="faint">{i + 1}.</span> {m.name}</td>
                <td>
                  {canEdit ? (
                    <select value={m.status} aria-label={`Status of ${m.name}`} style={{ width: "auto" }} onChange={(e) => patch(m.id, { status: e.target.value })}>
                      {MILESTONE_STATUS.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
                    </select>
                  ) : <span className={`chip ${m.status === "done" ? "pass" : m.status === "blocked" ? "blocker" : "neutral"}`}>{m.status.replace("_", " ")}</span>}
                </td>
                <td>
                  {canEdit ? <input type="date" value={m.due_date ?? ""} aria-label={`Due date of ${m.name}`} style={{ width: "auto" }}
                    onChange={(e) => e.target.value && patch(m.id, { due_date: e.target.value })} /> : date(m.due_date)}
                </td>
                <td>{dateTime(m.completed_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Message error={error} />
    </Panel>
  );
}

function Audit({ clientId, stamp }: { clientId: number; stamp: string }) {
  const rows = useLoad(() => api<AuditRow[]>(`/api/clients/${clientId}/audit?limit=40`), [clientId, stamp]);
  return (
    <Panel title="Audit trail" intro="Every approval, configuration change and file event, newest first. Entries are hash-chained, so editing or deleting one is detectable.">
      <div className="table-wrap">
        <table>
          <thead><tr><th>When</th><th>Who</th><th>What</th><th>Details</th></tr></thead>
          <tbody>
            {(rows.data ?? []).map((a) => (
              <tr key={a.id}>
                <td className="small" style={{ whiteSpace: "nowrap" }}>{dateTime(a.at)}</td>
                <td>{a.actor}</td>
                <td>{a.action.replace(".", ": ").replace("_", " ")}</td>
                <td className="faint" style={{ maxWidth: "28rem", overflowWrap: "anywhere" }}>{summarise(a.detail)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function summarise(detail: Record<string, unknown>): string {
  return Object.entries(detail)
    .filter(([, v]) => v !== null && v !== "" && !(Array.isArray(v) && v.length === 0))
    .slice(0, 5)
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${typeof v === "object" ? JSON.stringify(v).slice(0, 80) : String(v).slice(0, 80)}`)
    .join("; ");
}
