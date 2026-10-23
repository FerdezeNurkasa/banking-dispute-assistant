import { useState } from "react";
import { api } from "../api.js";

const DEMO_USERS = [
  { username: "arta", label: "Arta Gashi", role: "agent" },
  { username: "ana", label: "Ana Morina", role: "reviewer" },
  { username: "leon", label: "Leon Shala", role: "reviewer" },
];

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const session = await api.login(username.trim(), password);
      onLogin(session.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <form className="card login" onSubmit={submit}>
        <h1>Dispute Assistant</h1>
        <p className="muted">Sign in with your bank employee account</p>
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 autoComplete="current-password" required />
        </label>
        {error && <div className="error">{error}</div>}
        <button className="primary" disabled={loading}>{loading ? "Signing in…" : "Sign in"}</button>

        <div className="demo-users">
          <span className="label">Demo accounts (password from DEMO_PASSWORD, default Demo!2026)</span>
          {DEMO_USERS.map((u) => (
            <button type="button" key={u.username} onClick={() => setUsername(u.username)}>
              {u.label} · {u.role}
            </button>
          ))}
        </div>
      </form>
    </div>
  );
}