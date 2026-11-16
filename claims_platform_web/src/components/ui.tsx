import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ApiError } from "../api";
import { STATUS_LABEL } from "../format";
import type { Check } from "../types";

export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // The caller lists what the loader depends on, as with useEffect.
  const run = useCallback(load, deps);
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await run());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [run]);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { data, error, loading, reload, setData };
}

/** Wraps an action: shows its error, or a confirmation line, and refreshes the screen afterwards. */
export function useAction(after?: () => void | Promise<void>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<string[]>([]);
  const [done, setDone] = useState<string | null>(null);
  async function act<T>(fn: () => Promise<T>, success?: string): Promise<T | undefined> {
    setBusy(true);
    setError(null);
    setFields([]);
    setDone(null);
    try {
      const out = await fn();
      if (success) setDone(success);
      if (after) await after();
      return out;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      if (e instanceof ApiError) setFields(e.fields);
      return undefined;
    } finally {
      setBusy(false);
    }
  }
  return { act, busy, error, fields, done, clear: () => { setError(null); setDone(null); } };
}

export function Message({ error, done }: { error?: string | null; done?: string | null }) {
  if (error) return <p className="message error" role="alert">{error}</p>;
  if (done) return <p className="message ok" role="status">{done}</p>;
  return null;
}

export function Panel({ title, intro, actions, children }: { title: string; intro?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>{title}</h2>
          {intro && <p className="muted small">{intro}</p>}
        </div>
        {actions && <div className="row">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

export function Severity({ value }: { value: string }) {
  return <span className={`chip ${value === "blocker" ? "blocker" : "warning"}`}>{value === "blocker" ? "Blocker" : "Warning"}</span>;
}

export function Status({ value }: { value: string }) {
  const tone = value === "resolved" ? "pass" : value === "accepted" ? "action" : value === "reopened" ? "blocker" : "neutral";
  return <span className={`chip ${tone}`}>{STATUS_LABEL[value] ?? value}</span>;
}

export function Decision({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="chip neutral">Not validated</span>;
  return <span className={`chip ${value === "Ready" ? "pass" : "blocker"}`}>{value}</span>;
}

export function RunStatus({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="chip neutral">No run</span>;
  const tone = value === "completed" ? "pass" : value === "failed" || value === "interrupted" ? "blocker" : "action";
  const label = { queued: "Queued", running: "Running", completed: "Completed", failed: "Failed", interrupted: "Interrupted" }[value] ?? value;
  return <span className={`chip ${tone}`}>{label}</span>;
}

export function Checklist({ checks }: { checks: Check[] }) {
  return (
    <ul className="checklist">
      {checks.map((c) => (
        <li key={c.key}>
          <span className={`mark ${c.ok ? "ok" : "no"}`} aria-hidden="true">{c.ok ? "✓" : "!"}</span>
          <span>
            {c.label}
            <span className="visually-hidden">{c.ok ? " (passed)" : " (not yet)"}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Figure({ value, what, tone }: { value: ReactNode; what: string; tone?: "blocker" | "warning" | "pass" }) {
  return (
    <div className={`figure${tone ? ` ${tone}` : ""}`}>
      <div className="value">{value}</div>
      <div className="what">{what}</div>
    </div>
  );
}
