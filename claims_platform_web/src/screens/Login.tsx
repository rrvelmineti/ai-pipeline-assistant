import { useState, type FormEvent } from "react";
import { api, setToken } from "../api";
import { Message } from "../components/ui";
import type { User } from "../types";

export function Login({ onSignedIn }: { onSignedIn: (u: User) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ token: string; user: User }>("/api/auth/login", { json: { username, password } });
      setToken(r.token);
      onSignedIn(r.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="login-card">
        <div className="stack" style={{ gap: "0.35rem" }}>
          <h1>Claims Onboarding</h1>
          <p className="muted">Take each new client's claims file from first upload to an approved go-live.</p>
        </div>
        <form className="panel" onSubmit={submit} aria-label="Sign in">
          <label className="field">
            Username
            <input type="text" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label className="field">
            Password
            <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          <Message error={error} />
          <button className="btn primary" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
        <p className="faint">
          Pilot with synthetic data only. Not HIPAA-compliant; never upload real patient records.
        </p>
      </div>
    </div>
  );
}
