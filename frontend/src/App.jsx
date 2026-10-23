import { useCallback, useEffect, useState } from "react";
import { api, getSession, setSession } from "./api.js";
import Login from "./components/Login.jsx";
import NewDisputeForm from "./components/NewDisputeForm.jsx";
import DisputeList from "./components/DisputeList.jsx";
import DisputeDetail from "./components/DisputeDetail.jsx";
import Dashboard from "./components/Dashboard.jsx";

const FILTERS = [
  { value: "", label: "All" },
  { value: "needs_review", label: "Needs review" },
  { value: "resolved", label: "Resolved" },
];

function DisputesView({ user }) {
  const [disputes, setDisputes] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [filter, setFilter] = useState(user.role === "reviewer" ? "needs_review" : "");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setError("");
      setDisputes(query.trim() ? await api.search(query.trim()) : await api.disputes(filter));
    } catch (e) {
      setError(e.message);
    }
  }, [filter, query]);

  useEffect(() => {
    const t = setTimeout(load, 250); // debounce typing in the search box
    return () => clearTimeout(t);
  }, [load]);

  return (
    <>
      {error && <div className="error">{error}</div>}
      <main>
        <section className="left">
          <NewDisputeForm onCreated={(d) => { setSelectedId(d.id); load(); }} />
          <div className="card">
            <div className="list-header">
              <h2>Disputes</h2>
              <input placeholder="Search…" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
            {!query && (
              <div className="tabs">
                {FILTERS.map((f) => (
                  <button key={f.value} className={filter === f.value ? "active" : ""} onClick={() => setFilter(f.value)}>
                    {f.label}
                  </button>
                ))}
              </div>
            )}
            <DisputeList disputes={disputes} selectedId={selectedId} onSelect={setSelectedId} />
          </div>
        </section>
        <section className="right">
          {selectedId ? (
            <DisputeDetail id={selectedId} user={user} onChanged={load} />
          ) : (
            <div className="card empty">Submit a dispute or select one from the list.</div>
          )}
        </section>
      </main>
    </>
  );
}

export default function App() {
  const [user, setUser] = useState(getSession()?.user || null);
  const [view, setView] = useState("disputes");

  useEffect(() => {
    const onLogout = () => { setUser(null); setView("disputes"); };
    window.addEventListener("auth:logout", onLogout);
    return () => window.removeEventListener("auth:logout", onLogout);
  }, []);

  const logout = () => {
    setSession(null);
    setUser(null);
    setView("disputes"); // the next person to log in starts on the disputes page
  };

  if (!user) return <Login onLogin={setUser} />;

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Dispute Assistant</h1>
          <p>Multi-agent review of card transaction disputes, with human approval for risky cases</p>
        </div>
        <div className="user-chip">
          <span><b>{user.full_name}</b> · {user.role}</span>
          <button onClick={logout}>Log out</button>
        </div>
      </header>

      <nav className="tabs main-nav">
        <button className={view === "disputes" ? "active" : ""} onClick={() => setView("disputes")}>Disputes</button>
        <button className={view === "analytics" ? "active" : ""} onClick={() => setView("analytics")}>Analytics</button>
      </nav>

      {view === "disputes" ? <DisputesView user={user} /> : <Dashboard />}
    </div>
  );
}