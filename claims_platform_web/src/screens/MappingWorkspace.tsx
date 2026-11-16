import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Message, Panel, RunStatus, useAction, useLoad } from "../components/ui";
import { LEVEL_LABEL, canAnalyse, canApprove, dateTime, n } from "../format";
import type { MappingInfo, RuleSetInfo, Submission } from "../types";
import type { ClientScreenProps } from "./props";

const LEVEL_TONE: Record<string, string> = { high: "pass", medium: "action", low: "warning", ambiguous: "warning", none: "blocker" };

export function MappingWorkspace({ client, user, refresh, stamp }: ClientScreenProps) {
  const subs = useLoad(() => api<Submission[]>(`/api/clients/${client.id}/submissions`), [client.id, stamp]);
  const maps = useLoad(() => api<MappingInfo[]>(`/api/clients/${client.id}/mappings`), [client.id, stamp]);
  const reloadAll = async () => { await Promise.all([maps.reload(), subs.reload()]); await refresh(); };
  const working = maps.data?.find((m) => m.status === "draft" || m.status === "rejected");
  const pending = maps.data?.find((m) => m.status === "pending_approval");
  const approved = maps.data?.find((m) => m.status === "approved");
  const latest = subs.data?.[0];

  return (
    <div className="stack">
      <Panel title="Files received" intro="Every upload is kept, encrypted, with its fingerprint. Re-sending the latest file again is ignored.">
        {subs.data && subs.data.length === 0 ? (
          <div className="empty">No file yet. Upload the client's claims extract to start mapping.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>File</th><th>Name</th><th>Received</th><th className="right">Columns</th><th className="right">Size</th><th>Latest run</th></tr></thead>
              <tbody>
                {(subs.data ?? []).map((s) => (
                  <tr key={s.id}>
                    <td className="num">#{s.sequence}</td>
                    <td>{s.filename}{s.header_error && <div className="message error">{s.header_error}</div>}</td>
                    <td>{dateTime(s.uploaded_at)}</td>
                    <td className="right">{s.headers.length}</td>
                    <td className="right">{n(Math.round(s.size_bytes / 1024))} KB</td>
                    <td><RunStatus value={s.run?.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {working && canAnalyse(user.role) ? (
        <MappingEditor key={working.id} mapping={working} onSaved={reloadAll} />
      ) : pending ? (
        <MappingReview mapping={pending} canReview={canApprove(user.role) && pending.author_id !== user.id}
          isAuthor={pending.author_id === user.id} onDone={reloadAll} />
      ) : working ? (
        <Panel title={`Column mapping, version ${working.version}, in preparation`}
          intro={`${working.author ?? "An analyst"} is confirming the suggested columns. It comes to an approver once it is sent.`}>
          <MappingTable mapping={working} />
        </Panel>
      ) : (
        <StartMapping latest={latest} approved={approved} canStart={canAnalyse(user.role)} onStarted={reloadAll} />
      )}

      <MappingHistory maps={maps.data ?? []} canTemplate={canAnalyse(user.role)} onDone={maps.reload} />
      <Rules clientId={client.id} userId={user.id} canDraft={canAnalyse(user.role)} canReview={canApprove(user.role)} onDone={refresh} stamp={stamp} />
    </div>
  );
}

function StartMapping({ latest, approved, canStart, onStarted }: {
  latest?: Submission; approved?: MappingInfo; canStart: boolean; onStarted: () => Promise<void>;
}) {
  const [useAi, setUseAi] = useState(false);
  const { act, busy, error } = useAction(onStarted);
  const fits = approved && latest && Object.values(approved.mapping).every((c) => !c || latest.headers.includes(c));
  return (
    <Panel title="Column mapping"
      intro={approved ? `Version ${approved.version} is approved${fits ? " and fits the latest file." : ", but the latest file has a different layout."}` : "No mapping is approved yet."}>
      {!latest ? (
        <div className="empty">Upload a file first.</div>
      ) : canStart ? (
        <div className="stack" style={{ gap: "0.75rem" }}>
          <p className="muted">
            Suggestions come from matching column names{useAi ? " and from Gemini, which sees column headings only, never values" : ""}.
            Anything that is not a clear match must be confirmed by you and approved by someone else.
          </p>
          <div className="row">
            <button className="btn primary" disabled={busy}
              onClick={() => act(() => api(`/api/submissions/${latest.id}/mappings`, { json: { use_ai: useAi } }))}>
              {busy ? "Suggesting…" : `Suggest a mapping for file #${latest.sequence}`}
            </button>
            <label className="check"><input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} /> Ask Gemini as well</label>
          </div>
          <Message error={error} />
        </div>
      ) : (
        <p className="muted">An implementation analyst prepares the mapping.</p>
      )}
    </Panel>
  );
}

function MappingEditor({ mapping, onSaved }: { mapping: MappingInfo; onSaved: () => Promise<void> }) {
  const fields = Object.keys(mapping.suggestions);
  const [chosen, setChosen] = useState<Record<string, string | null>>(mapping.mapping);
  const [confirmed, setConfirmed] = useState<Set<string>>(new Set(mapping.confirmed_fields));
  const [note, setNote] = useState(mapping.note);
  const { act, busy, error, fields: unconfirmed, done } = useAction(onSaved);
  useEffect(() => setChosen(mapping.mapping), [mapping]);
  const changed = useMemo(() => fields.filter((f) => (chosen[f] ?? null) !== mapping.suggestions[f].column), [chosen, fields, mapping]);
  const used = Object.values(chosen).filter(Boolean) as string[];
  const toConfirm = fields.filter((f) => mapping.suggestions[f].needs_confirmation && !changed.includes(f) && !confirmed.has(f));

  function save(submit: boolean) {
    return act(() => api(`/api/mappings/${mapping.id}`, {
      method: "PUT", json: { mapping: chosen, confirmed_fields: [...confirmed], note, submit },
    }), submit ? "Sent for approval." : "Draft saved.");
  }

  return (
    <Panel title={`Column mapping, version ${mapping.version} (draft)`}
      intro={<>Choose the client column for each platform field. {mapping.ai_error && <span>Gemini was not used: {mapping.ai_error}</span>}
        {mapping.template && <span> Started from the saved template “{mapping.template}”.</span>}</>}>
      {mapping.status === "rejected" && <p className="message error">Returned by {mapping.approver}: {mapping.review_comment}</p>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Platform field</th><th>Suggestion</th><th>Client column</th><th>Confirmed</th></tr></thead>
          <tbody>
            {fields.map((f) => {
              const s = mapping.suggestions[f];
              const isChanged = changed.includes(f);
              const flagged = unconfirmed.includes(f) || (toConfirm.includes(f) && unconfirmed.length > 0);
              return (
                <tr key={f} className={flagged ? "selected" : undefined}>
                  <td>
                    <strong>{f}</strong> {s.required ? <span className="faint">required</span> : <span className="faint">optional</span>}
                    <div className="faint">{s.description}</div>
                  </td>
                  <td>
                    <span className={`chip ${LEVEL_TONE[s.level]}`}>{LEVEL_LABEL[s.level]}</span>{" "}
                    <span className="small">{s.column ?? "nothing suggested"}</span>
                    <div className="faint">{s.reason}{s.alternatives.length > 0 && ` Also possible: ${s.alternatives.join(", ")}.`}</div>
                  </td>
                  <td style={{ minWidth: "14rem" }}>
                    <select value={chosen[f] ?? ""} aria-label={`Client column for ${f}`}
                      onChange={(e) => setChosen({ ...chosen, [f]: e.target.value || null })}>
                      <option value="">{s.required ? "Choose a column" : "Not provided by the client"}</option>
                      {mapping.headers.map((h) => (
                        <option key={h} value={h} disabled={used.includes(h) && chosen[f] !== h}>{h}</option>
                      ))}
                    </select>
                    {isChanged && <div className="faint">Changed from the suggestion; logged as a correction.</div>}
                  </td>
                  <td className="nowrap">
                    {s.needs_confirmation && !isChanged ? (
                      <label className="check">
                        <input type="checkbox" checked={confirmed.has(f)}
                          onChange={(e) => {
                            const next = new Set(confirmed);
                            if (e.target.checked) next.add(f); else next.delete(f);
                            setConfirmed(next);
                          }} />
                        I checked this
                      </label>
                    ) : (
                      <span className="faint">{isChanged ? "Your choice" : "Clear match"}</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="stack" style={{ marginTop: "1rem", gap: "0.75rem" }}>
        <label className="field">Note for the approver
          <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="For example: the vendor's data dictionary says Servicing Provider NPI is the rendering NPI." style={{ minHeight: "4rem" }} />
        </label>
        <p className="muted small">
          {changed.length} changed from the suggestions. {toConfirm.length ? `${toConfirm.length} still to confirm: ${toConfirm.join(", ")}.` : "Every uncertain field is confirmed."}
        </p>
        <div className="row">
          <button className="btn primary" disabled={busy} onClick={() => save(true)}>Send for approval</button>
          <button className="btn" disabled={busy} onClick={() => save(false)}>Save draft</button>
        </div>
        <Message error={error} done={done} />
      </div>
    </Panel>
  );
}

function MappingReview({ mapping, canReview, isAuthor, onDone }: { mapping: MappingInfo; canReview: boolean; isAuthor: boolean; onDone: () => Promise<void> }) {
  const [comment, setComment] = useState("");
  const { act, busy, error } = useAction(onDone);
  const review = (approve: boolean) => act(() => api(`/api/mappings/${mapping.id}/review`, { json: { approve, comment } }));
  return (
    <Panel title={`Column mapping, version ${mapping.version}, waiting for approval`} intro={`Prepared by ${mapping.author}. ${mapping.note}`}>
      <MappingTable mapping={mapping} />
      {mapping.corrections.length > 0 && (
        <p className="muted small" style={{ marginTop: "0.75rem" }}>
          The analyst changed {mapping.corrections.length} suggestions: {mapping.corrections.map((c) => `${c.field} (${c.suggested_column ?? "none"} to ${c.chosen_column ?? "none"})`).join("; ")}.
        </p>
      )}
      {canReview ? (
        <div className="stack" style={{ marginTop: "1rem", gap: "0.75rem" }}>
          <label className="field">Comment<textarea value={comment} onChange={(e) => setComment(e.target.value)} style={{ minHeight: "4rem" }} placeholder="Required when returning the mapping" /></label>
          <div className="row">
            <button className="btn primary" disabled={busy} onClick={() => review(true)}>Approve mapping</button>
            <button className="btn danger" disabled={busy} onClick={() => review(false)}>Return to analyst</button>
          </div>
          <Message error={error} />
        </div>
      ) : (
        <p className="muted small" style={{ marginTop: "0.75rem" }}>
          {isAuthor ? "You prepared this mapping, so someone else must approve it." : "An approver reviews this mapping."}
        </p>
      )}
    </Panel>
  );
}

function MappingTable({ mapping }: { mapping: MappingInfo }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Platform field</th><th>Client column</th><th>Suggestion confidence</th><th>Confirmed by analyst</th></tr></thead>
        <tbody>
          {Object.entries(mapping.mapping).map(([f, c]) => {
            const s = mapping.suggestions[f];
            return (
              <tr key={f}>
                <td>{f}</td>
                <td>{c ?? <span className="faint">Not provided</span>}</td>
                <td><span className={`chip ${LEVEL_TONE[s.level]}`}>{LEVEL_LABEL[s.level]}</span></td>
                <td>{mapping.confirmed_fields.includes(f) ? "Yes" : mapping.corrections.some((x) => x.field === f) ? "Changed" : "–"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MappingHistory({ maps, canTemplate, onDone }: { maps: MappingInfo[]; canTemplate: boolean; onDone: () => void }) {
  const [name, setName] = useState("");
  const { act, busy, error, done } = useAction(onDone);
  const approved = maps.find((m) => m.status === "approved");
  const history = maps.filter((m) => m.status !== "discarded");
  if (history.length === 0) return null;
  return (
    <Panel title="Mapping versions" intro="Who prepared and who approved each version.">
      <div className="table-wrap">
        <table>
          <thead><tr><th>Version</th><th>Status</th><th>Prepared by</th><th>Approved by</th><th>Approved</th><th className="right">Corrections</th></tr></thead>
          <tbody>
            {history.map((m) => (
              <tr key={m.id}>
                <td>{m.version}</td>
                <td><span className={`chip ${m.status === "approved" ? "pass" : "neutral"}`}>{m.status.replace("_", " ")}</span></td>
                <td>{m.author ?? "–"}</td>
                <td>{m.approver ?? "–"}</td>
                <td>{dateTime(m.approved_at)}</td>
                <td className="right">{m.corrections.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {approved && canTemplate && (
        <div className="row" style={{ marginTop: "1rem" }}>
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Template name, such as Vendor X extract" style={{ maxWidth: "22rem" }} aria-label="Template name" />
          <button className="btn" disabled={busy || name.trim().length < 3}
            onClick={() => act(() => api(`/api/mappings/${approved.id}/template`, { json: { name } }), "Saved. Files with the same columns will start from this mapping.")}>
            Save version {approved.version} as a template
          </button>
        </div>
      )}
      <div style={{ marginTop: "0.5rem" }}><Message error={error} done={done} /></div>
    </Panel>
  );
}

function Rules({ clientId, userId, canDraft, canReview, onDone, stamp }: {
  clientId: number; userId: number; canDraft: boolean; canReview: boolean; onDone: () => void; stamp: string;
}) {
  const sets = useLoad(() => api<RuleSetInfo[]>(`/api/clients/${clientId}/rulesets`), [clientId, stamp]);
  const current = sets.data?.find((r) => r.status === "approved");
  const drafts = (sets.data ?? []).filter((r) => r.status === "draft");
  const [text, setText] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [comment, setComment] = useState("");
  const after = async () => { await sets.reload(); onDone(); };
  const { act, busy, error, done } = useAction(after);
  return (
    <Panel title="Onboarding rules" intro={current ? `Version ${current.version} is in force. ${current.note}` : "No approved rules."}>
      {current && (
        <details>
          <summary className="small">Show the rules in force</summary>
          <pre className="letter">{current.text}</pre>
        </details>
      )}
      {drafts.map((d) => (
        <div key={d.id} className="stack" style={{ gap: "0.5rem", marginTop: "1rem" }}>
          <p><strong>Proposed version {d.version}</strong> by {d.author}: {d.note || "no note"}</p>
          <details><summary className="small">Show the proposed rules</summary><pre className="letter">{d.text}</pre></details>
          {canReview && d.author_id !== userId ? (
            <div className="row">
              <input type="text" value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comment" aria-label="Review comment" style={{ maxWidth: "22rem" }} />
              <button className="btn primary" disabled={busy} onClick={() => act(() => api(`/api/rulesets/${d.id}/review`, { json: { approve: true, comment } }), "Rules approved.")}>Approve rules</button>
              <button className="btn danger" disabled={busy} onClick={() => act(() => api(`/api/rulesets/${d.id}/review`, { json: { approve: false, comment } }))}>Reject</button>
            </div>
          ) : (
            <p className="faint">Waiting for an approver other than {d.author}.</p>
          )}
        </div>
      ))}
      {canDraft && current && drafts.length === 0 && (
        text === null ? (
          <button className="btn" style={{ marginTop: "1rem" }} onClick={() => setText(current.text)}>Propose a rule change</button>
        ) : (
          <div className="stack" style={{ gap: "0.75rem", marginTop: "1rem" }}>
            <label className="field">Rules (one field per line: field | description | rules)
              <textarea className="code" value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} />
            </label>
            <label className="field">Why the change<input type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="For example: the client sends US-format dates" /></label>
            <div className="row">
              <button className="btn primary" disabled={busy}
                onClick={async () => { const ok = await act(() => api(`/api/clients/${clientId}/rulesets`, { json: { text, note } }), "Proposed. An approver must accept it before it is used."); if (ok) setText(null); }}>
                Propose version {(sets.data?.[0]?.version ?? 0) + 1}
              </button>
              <button className="btn" onClick={() => setText(null)}>Cancel</button>
            </div>
          </div>
        )
      )}
      <div style={{ marginTop: "0.75rem" }}><Message error={error} done={done} /></div>
    </Panel>
  );
}
