import { useEffect, useRef, useState } from "react";
import { api, hasToken, setToken, whenSignedOut } from "./api";
import { StageTrack } from "./components/StageTrack";
import { Message, useAction, useLoad } from "./components/ui";
import { ROLE_LABEL, canAnalyse, isInternal, plural } from "./format";
import { Dashboard } from "./screens/Dashboard";
import { GoLive } from "./screens/GoLive";
import { Login } from "./screens/Login";
import { MappingWorkspace } from "./screens/MappingWorkspace";
import { ResubmissionTracker } from "./screens/ResubmissionTracker";
import { ValidationExceptions } from "./screens/ValidationExceptions";
import type { ClientDetail, User } from "./types";

type Tab = "mapping" | "validation" | "resubmissions" | "golive";
type Route = { view: "dashboard" } | { view: "client"; id: number; tab: Tab | null };

const TABS: { key: Tab; label: string; internal: boolean }[] = [
  { key: "mapping", label: "Data mapping", internal: true },
  { key: "validation", label: "Validation and exceptions", internal: false },
  { key: "resubmissions", label: "Resubmissions", internal: false },
  { key: "golive", label: "Go-live and reporting", internal: true },
];

export function parseRoute(hash: string): Route {
  const m = hash.match(/^#\/clients\/(\d+)(?:\/(mapping|validation|resubmissions|golive))?/);
  return m ? { view: "client", id: Number(m[1]), tab: (m[2] as Tab) ?? null } : { view: "dashboard" };
}

function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const on = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checked, setChecked] = useState(!hasToken());
  const route = useRoute();

  useEffect(() => {
    whenSignedOut(() => setUser(null));
    if (hasToken()) {
      api<{ user: User }>("/api/auth/me")
        .then((r) => setUser(r.user))
        .catch(() => setToken(null))
        .finally(() => setChecked(true));
    }
  }, []);

  if (!checked) return null;
  if (!user) return <Login onSignedIn={setUser} />;

  async function signOut() {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      setToken(null);
      setUser(null);
      window.location.hash = "";
    }
  }

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#/">
            <strong>Claims Onboarding</strong>
            <span>Pilot with synthetic data</span>
          </a>
          <span className="spacer" />
          <div className="whoami">
            <b>{user.display_name}</b>
            <div>{ROLE_LABEL[user.role]}</div>
          </div>
          <button className="btn small" onClick={signOut}>Sign out</button>
        </div>
      </header>
      <main>
        {route.view === "dashboard" ? <Dashboard user={user} /> : <ClientView key={route.id} id={route.id} tab={route.tab} user={user} />}
        <p className="notice">
          Synthetic data only. This pilot is not HIPAA-compliant: do not upload real patient records or confidential
          client files.
        </p>
      </main>
    </>
  );
}

function ClientView({ id, tab, user }: { id: number; tab: Tab | null; user: User }) {
  const { data: client, error, reload } = useLoad(() => api<ClientDetail>(`/api/clients/${id}`), [id]);
  if (error) return <Message error={error === "Not found." ? "This client does not exist or you do not have access to it." : error} />;
  if (!client) return <p className="muted">Loading client…</p>;
  const tabs = TABS.filter((t) => isInternal(user.role) || !t.internal);
  const early = ["Setup", "Mapping"].includes(client.readiness.stage);
  const active = tab ?? (isInternal(user.role) ? (early ? "mapping" : "validation") : "validation");
  const passed = client.readiness.checks.filter((c) => c.ok).length;
  const r = client.readiness;
  const stamp = [r.stage, r.latest_submission, r.latest_run_status, r.run?.id, r.open_blockers, r.open_warnings,
    r.mapping_version, r.rule_set_version, r.approval?.id, r.export?.status].join("|");
  const props = { client, user, refresh: reload, stamp };
  return (
    <div>
      <div className="client-head">
        <div className="row between">
          <div className="title">
            <h1>{client.name}</h1>
            <span className="code">{client.code}</span>
          </div>
          {(canAnalyse(user.role) || user.role === "client_contact") && <Upload clientId={client.id} onDone={reload} />}
        </div>
        <StageTrack stage={client.readiness.stage} />
        <p className="muted small">
          {client.readiness.stage}. {passed} of {client.readiness.checks.length} readiness checks pass
          {client.readiness.open_blockers > 0 && `; ${plural(client.readiness.open_blockers, "open blocker exception")}`}
          {client.readiness.open_warnings > 0 && `; ${plural(client.readiness.open_warnings, "open warning")}`}.
        </p>
      </div>
      <nav className="tabs" aria-label="Client steps">
        {tabs.map((t) => (
          <a key={t.key} href={`#/clients/${client.id}/${t.key}`} aria-current={active === t.key ? "page" : undefined}>
            {t.label}
          </a>
        ))}
      </nav>
      {active === "mapping" && isInternal(user.role) && <MappingWorkspace {...props} />}
      {active === "validation" && <ValidationExceptions {...props} />}
      {active === "resubmissions" && <ResubmissionTracker {...props} />}
      {active === "golive" && isInternal(user.role) && <GoLive {...props} />}
    </div>
  );
}

function Upload({ clientId, onDone }: { clientId: number; onDone: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [note, setNote] = useState<string | null>(null);
  const { act, busy, error } = useAction(onDone);
  async function onPick(file: File | undefined) {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    setNote(null);
    const out = await act(() => api<{ detail: string }>(`/api/clients/${clientId}/submissions`, { form }));
    if (out) setNote(out.detail);
    if (input.current) input.current.value = "";
  }
  return (
    <div className="stack" style={{ gap: "0.4rem", justifyItems: "end" }}>
      <label className="btn primary">
        {busy ? "Uploading…" : "Upload client file"}
        <input ref={input} type="file" accept=".csv,text/csv" className="visually-hidden" disabled={busy}
          onChange={(e) => void onPick(e.target.files?.[0])} />
      </label>
      {error ? <Message error={error} /> : note ? <Message done={note} /> : <span className="faint">CSV in UTF-8, up to 20 MB</span>}
    </div>
  );
}
