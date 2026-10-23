import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import NewDisputeForm from "./components/NewDisputeForm.jsx";
import DisputeList from "./components/DisputeList.jsx";
import DisputeDetail from "./components/DisputeDetail.jsx";

const FILTERS = [
  { value: "", label: "All" },
  { value: "needs_review", label: "Needs review" },
  { value: "resolved", label: "Resolved" },
];

export default function App() {
  const [disputes, setDisputes] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [filter, setFilter] = useState("");
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

  const onCreated = (dispute) => {
    setSelectedId(dispute.id);
    load();
  };

  return (
    <div className="app">
      <header>
        <h1>Dispute Assistant</h1>
        <p>Multi-agent review of card transaction disputes, with human approval for risky cases</p>
      </header>

      {error && <div className="error">{error}</div>}

      <main>
        <section className="left">
          <NewDisputeForm onCreated={onCreated} />
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
            <DisputeDetail id={selectedId} onChanged={load} />
          ) : (
            <div className="card empty">Submit a dispute or select one from the list.</div>
          )}
        </section>
      </main>
    </div>
  );
}