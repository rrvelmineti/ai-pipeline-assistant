import { useState, type FormEvent } from "react";
import { api } from "../api";
import { StageTrack } from "../components/StageTrack";
import { Figure, Message, Panel, RunStatus, useAction, useLoad } from "../components/ui";
import { canAnalyse, date, isInternal, n, pct, seconds } from "../format";
import type { ClientRow, Kpi, Metrics, Portfolio, User } from "../types";

function kpiValue(k: Kpi) {
  if (k.value === null) return "–";
  if (k.name.includes("rate") || k.name.includes("completed") || k.name.includes("Exports")) return pct(k.value);
  return n(k.value);
}

export function Dashboard({ user }: { user: User }) {
  const clients = useLoad(() => api<ClientRow[]>("/api/clients"), []);
  const internal = isInternal(user.role);
  const portfolio = useLoad(() => (internal ? api<Portfolio>("/api/reports/portfolio") : Promise.resolve(null)), [internal]);
  const metrics = useLoad(() => (internal ? api<Metrics>("/api/metrics/processing") : Promise.resolve(null)), [internal]);
  const rows = clients.data ?? [];
  const ready = rows.filter((c) => c.stage === "Ready for approval").length;
  const blockers = rows.reduce((s, c) => s + c.open_blockers, 0);

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Client onboarding</h1>
        <p className="muted">Where every client stands on the way to go-live, and what is holding each one back.</p>
      </div>

      {rows.length > 0 && (
        <div className="figures">
          <Figure value={n(rows.length)} what="Clients you can see" />
          <Figure value={n(ready)} what="Ready for approval" tone={ready ? "pass" : undefined} />
          <Figure value={n(rows.filter((c) => c.stage === "Live").length)} what="Live" />
          <Figure value={n(blockers)} what="Open blocker exceptions" tone={blockers ? "blocker" : undefined} />
        </div>
      )}

      <Panel title="Clients" intro="Select a client to work on its mapping, exceptions, resubmissions and go-live.">
        <Message error={clients.error} />
        {rows.length === 0 && !clients.loading ? (
          <div className="empty">
            {canAnalyse(user.role) ? "No clients yet. Add the first one below." : "No clients have been shared with you yet."}
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Client</th>
                  <th>Stage</th>
                  <th className="right">Checks</th>
                  <th className="right">Blockers</th>
                  <th className="right">Warnings</th>
                  <th>Latest file</th>
                  <th>Target go-live</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id} className="clickable" onClick={() => (window.location.hash = `#/clients/${c.id}`)}>
                    <td>
                      <a href={`#/clients/${c.id}`} onClick={(e) => e.stopPropagation()}>{c.name}</a>
                      <div className="faint">{c.code}</div>
                    </td>
                    <td>
                      <div className="stage-cell">
                        <StageTrack stage={c.stage} compact />
                        <span className="stage-name">{c.stage}</span>
                      </div>
                    </td>
                    <td className="right">{c.checks_passed} of {c.checks_total}</td>
                    <td className="right">{c.open_blockers ? <span className="chip blocker">{c.open_blockers}</span> : "0"}</td>
                    <td className="right">{c.open_warnings ? <span className="chip warning">{c.open_warnings}</span> : "0"}</td>
                    <td>
                      {c.latest_submission ? <>#{c.latest_submission} <RunStatus value={c.latest_run_status} /></> : <span className="faint">None yet</span>}
                    </td>
                    <td>{date(c.go_live_target)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {canAnalyse(user.role) && <AddClient onAdded={clients.reload} />}

      {internal && portfolio.data && (
        <Panel title="Onboarding measures"
          intro="Computed from the platform's own records. Each figure shows how many clients or files it is based on.">
          <div className="table-wrap">
            <table>
              <thead><tr><th>Measure</th><th className="right">Value</th><th className="right">Based on</th><th>How it is measured</th></tr></thead>
              <tbody>
                {portfolio.data.kpis.map((k) => (
                  <tr key={k.name}>
                    <td>{k.name}</td>
                    <td className="right num">{kpiValue(k)}</td>
                    <td className="right num">{k.n}</td>
                    <td className="muted small">{k.definition}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="faint" style={{ marginTop: "0.75rem" }}>{portfolio.data.baseline}</p>
        </Panel>
      )}

      {internal && metrics.data && <Processing m={metrics.data} />}
    </div>
  );
}

function Processing({ m }: { m: Metrics }) {
  return (
    <Panel title="Processing" intro="Validation runs and exports for the clients you can see.">
      <div className="figures">
        <Figure value={n(m.runs.total)} what="Validation runs" />
        <Figure value={pct(m.runs.first_attempt_success_rate)} what="Completed on first attempt" />
        <Figure value={seconds(m.runs.median_ms)} what="Median run time" />
        <Figure value={seconds(m.runs.p95_ms)} what="95th percentile run time" />
        <Figure value={n(m.runs.rows_per_second)} what="Rows checked per second" />
        <Figure value={n(m.exports.records_loaded)} what="Claims loaded downstream" />
        <Figure value={n(m.exports.duplicates_skipped)} what="Duplicate claims refused" />
        <Figure value={`${m.exports.completed} of ${m.exports.total}`} what="Exports completed" />
      </div>
      {m.recent_runs.length > 0 && (
        <div className="table-wrap" style={{ marginTop: "1rem" }}>
          <table>
            <thead><tr><th>Run</th><th>Client</th><th>Status</th><th className="right">Attempts</th><th className="right">Rows</th><th className="right">Time</th><th>Decision</th></tr></thead>
            <tbody>
              {m.recent_runs.slice(0, 10).map((r) => (
                <tr key={r.id}>
                  <td className="num">{r.id}</td>
                  <td>{r.client}</td>
                  <td><RunStatus value={r.status} /></td>
                  <td className="right">{r.attempts}</td>
                  <td className="right">{n(r.rows_checked)}</td>
                  <td className="right">{seconds(r.duration_ms)}</td>
                  <td>{r.decision ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function AddClient({ onAdded }: { onAdded: () => void }) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const { act, busy, error, done } = useAction(onAdded);
  async function submit(e: FormEvent) {
    e.preventDefault();
    const out = await act(() => api("/api/clients", { json: { code: code.trim().toUpperCase(), name, go_live_target: target || null } }),
      "Client added with the baseline onboarding rules and a standard timeline.");
    if (out) { setCode(""); setName(""); setTarget(""); }
  }
  return (
    <Panel title="Add a client" intro="The client starts on the platform's baseline rules. You can propose client-specific rules later.">
      <form className="grid-3" onSubmit={submit}>
        <label className="field">Client code<input type="text" value={code} onChange={(e) => setCode(e.target.value)} placeholder="G-GROVE" pattern="[A-Za-z0-9-]{2,40}" required /></label>
        <label className="field">Client name<input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Grove Health Plan" required minLength={2} /></label>
        <label className="field">Target go-live<input type="date" value={target} onChange={(e) => setTarget(e.target.value)} /></label>
        <div className="row" style={{ alignSelf: "end" }}><button className="btn primary" disabled={busy}>Add client</button></div>
      </form>
      <div style={{ marginTop: "0.75rem" }}><Message error={error} done={done} /></div>
    </Panel>
  );
}
