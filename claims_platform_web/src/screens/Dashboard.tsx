import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import { Poster, glyph } from "../components/Poster";
import { StageTrack } from "../components/StageTrack";
import { Figure, Message, Panel, RunStatus, useAction, useLoad } from "../components/ui";
import { canAnalyse, date, isInternal, n, pct, plural, seconds } from "../format";
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

  const featured = pickFeatured(rows);
  const shelves = [
    { title: "Needs attention", items: rows.filter((c) => c.stage === "Remediation" || c.open_blockers > 0) },
    { title: "In progress", items: rows.filter((c) => ["Setup", "Mapping", "Validation"].includes(c.stage) && c.open_blockers === 0) },
    { title: "Ready for go-live", items: rows.filter((c) => ["Ready for approval", "Approved"].includes(c.stage) && c.open_blockers === 0) },
    { title: "Live", items: rows.filter((c) => c.stage === "Live" && c.open_blockers === 0) },
  ].filter((s) => s.items.length > 0);

  return (
    <div className="stack" style={{ gap: 0 }}>
      <h1 className="visually-hidden">Client onboarding</h1>
      {featured ? <Billboard client={featured} /> : <div style={{ height: "5rem" }} />}

      {rows.length > 0 && (
        <div className="figures home-figures">
          <Figure value={n(rows.length)} what="Clients you can see" />
          <Figure value={n(ready)} what="Ready for approval" tone={ready ? "pass" : undefined} />
          <Figure value={n(rows.filter((c) => c.stage === "Live").length)} what="Live" />
          <Figure value={n(blockers)} what="Open blocker exceptions" tone={blockers ? "blocker" : undefined} />
        </div>
      )}

      <Message error={clients.error} />
      {rows.length === 0 && !clients.loading && (
        <div className="empty">
          {canAnalyse(user.role) ? "No clients yet. Add the first one below." : "No clients have been shared with you yet."}
        </div>
      )}
      {shelves.map((s) => <Shelf key={s.title} title={s.title} clients={s.items} />)}

      <div className="stack">
      {rows.length > 0 && (
      <Panel title="All clients" intro="Every client as a list. Select a client to work on its mapping, exceptions, resubmissions and go-live.">
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
      </Panel>
      )}

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
    </div>
  );
}

// The billboard features the client that most needs a person: the most open blockers first, then
// a client waiting for approval, then the earliest in progress.
export function pickFeatured(rows: ClientRow[]): ClientRow | null {
  if (rows.length === 0) return null;
  const blocked = [...rows].filter((c) => c.open_blockers > 0).sort((a, b) => b.open_blockers - a.open_blockers);
  if (blocked.length) return blocked[0];
  const waiting = rows.find((c) => c.stage === "Ready for approval");
  if (waiting) return waiting;
  return rows.find((c) => c.stage !== "Live") ?? rows[0];
}

function lede(c: ClientRow): string {
  if (c.open_blockers > 0) {
    return `${plural(c.open_blockers, "blocker exception")} ${c.open_blockers === 1 ? "is" : "are"} holding this client back from go-live. Open the exceptions to see what the client needs to fix.`;
  }
  switch (c.stage) {
    case "Ready for approval": return "Every readiness check passes. This client is waiting for a second person to approve go-live.";
    case "Approved": return "Go-live is approved. The next step is the export to the claims system.";
    case "Live": return "Live: approved claims have been loaded downstream, each one exactly once.";
    case "Setup": return "A new client. The next step is the first file and its column mapping.";
    case "Mapping": return "The column mapping is being confirmed before the first full validation.";
    default: return `${c.checks_passed} of ${c.checks_total} readiness checks pass so far.`;
  }
}

function Billboard({ client: c }: { client: ClientRow }) {
  const label = c.open_blockers > 0 ? "Needs attention" : c.stage === "Ready for approval" ? "Waiting for approval" : "Featured client";
  return (
    <section className="hero" aria-label={`Featured client: ${c.name}`}>
      <Poster seed={c.code} label={glyph(c.code)} />
      <div className="hero-body">
        <div className="eyebrow"><span className="tag brand">{label}</span><span>{c.code}</span></div>
        <h2 className="hero-title">{c.name}</h2>
        <div className="meta">
          <span className={c.open_blockers ? "bad" : c.checks_passed === c.checks_total ? "good" : undefined}>
            {c.checks_passed} of {c.checks_total} checks pass
          </span>
          <span className="pill">{c.stage}</span>
          {c.open_blockers > 0 && <span className="bad">{plural(c.open_blockers, "blocker")}</span>}
          {c.open_warnings > 0 && <span>{plural(c.open_warnings, "warning")}</span>}
          {c.go_live_target && <span>Target {date(c.go_live_target)}</span>}
        </div>
        <p className="lede">{lede(c)}</p>
        <StageTrack stage={c.stage} />
        <div className="hero-actions">
          <a className="btn light big" href={`#/clients/${c.id}`}><span className="icon" aria-hidden="true">▶</span>Open client</a>
          <a className="btn big" href={`#/clients/${c.id}/validation`}><span className="icon" aria-hidden="true">ⓘ</span>Exceptions</a>
        </div>
      </div>
    </section>
  );
}

function Shelf({ title, clients }: { title: string; clients: ClientRow[] }) {
  const track = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ start: true, end: true });
  useEffect(() => {
    const el = track.current;
    if (!el) return;
    const on = () => setEdges({ start: el.scrollLeft <= 4, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 4 });
    on();
    el.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => { el.removeEventListener("scroll", on); window.removeEventListener("resize", on); };
  }, [clients.length]);
  const page = (dir: number) => track.current?.scrollBy({ left: dir * track.current.clientWidth * 0.85, behavior: "smooth" });
  return (
    <section className="shelf" aria-label={title}>
      <div className="shelf-head"><h2>{title}</h2><span className="count">{plural(clients.length, "client")}</span></div>
      <button className="shelf-arrow left" onClick={() => page(-1)} hidden={edges.start} aria-label={`Scroll ${title} left`}>‹</button>
      <div className="shelf-track" ref={track}>
        {clients.map((c) => <ClientCard key={c.id} c={c} />)}
      </div>
      <button className="shelf-arrow right" onClick={() => page(1)} hidden={edges.end} aria-label={`Scroll ${title} right`}>›</button>
    </section>
  );
}

function ClientCard({ c }: { c: ClientRow }) {
  return (
    <a className="card" href={`#/clients/${c.id}`}>
      <Poster seed={c.code} label={glyph(c.code)}>
        <div className="flag">
          {c.open_blockers > 0 && <span className="tag blocker">{plural(c.open_blockers, "blocker")}</span>}
          {c.open_warnings > 0 && <span className="tag warning">{plural(c.open_warnings, "warning")}</span>}
          {c.open_blockers === 0 && ["Ready for approval", "Approved"].includes(c.stage) && <span className="tag pass">Ready</span>}
          {c.stage === "Live" && <span className="tag light">Live</span>}
        </div>
        <div className="title">{c.name}</div>
      </Poster>
      <div className="info">
        <StageTrack stage={c.stage} compact />
        <div className="line"><b>{c.stage}</b><span>{c.checks_passed} of {c.checks_total} checks</span></div>
        <div className="line">
          <span>{c.latest_submission ? `File #${c.latest_submission}` : "No file yet"}</span>
          <span>{c.go_live_target ? `Target ${date(c.go_live_target)}` : "No target date"}</span>
        </div>
      </div>
    </a>
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
