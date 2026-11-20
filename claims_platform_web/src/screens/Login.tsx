import { useState, type FormEvent } from "react";
import { api, setToken } from "../api";
import { Poster } from "../components/Poster";
import { Message } from "../components/ui";
import type { User } from "../types";

// Decorative wall of poster art behind the sign-in card. Fixed seeds, so it never changes.
const WALL = Array.from({ length: 30 }, (_, i) => `wall-${i * 7 + 3}`);
const WALL_GLYPHS = ["A", "B", "C", "D", "E", "F"];

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
      <div className="login-wall" aria-hidden="true">
        {WALL.map((seed, i) => <Poster key={seed} seed={seed} label={WALL_GLYPHS[i % WALL_GLYPHS.length]} />)}
      </div>
      <div className="login-shade" aria-hidden="true" />
      <div className="brand"><strong>Claims Onboarding</strong></div>
      <div className="login-center">
        <div className="login-card">
          <div className="stack" style={{ gap: "0.5rem" }}>
            <h1>Sign in</h1>
            <p className="muted">Take each new client's claims file from first upload to an approved go-live.</p>
          </div>
          <form onSubmit={submit} aria-label="Sign in">
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
      <p className="login-foot">Synthetic data only · Pilot v1.0</p>
    </div>
  );
}
