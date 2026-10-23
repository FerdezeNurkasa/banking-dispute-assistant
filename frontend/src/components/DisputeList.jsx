export function StatusBadge({ status }) {
  const labels = { needs_review: "Needs review", resolved: "Resolved", processing: "Processing", failed: "Failed" };
  return <span className={`badge ${status}`}>{labels[status] || status}</span>;
}

export default function DisputeList({ disputes, selectedId, onSelect }) {
  if (!disputes.length) return <p className="muted">No disputes yet.</p>;
  return (
    <ul className="dispute-list">
      {disputes.map((d) => (
        <li key={d.id} className={d.id === selectedId ? "selected" : ""} onClick={() => onSelect(d.id)}>
          <div className="row">
            <strong>#{d.id} · {d.customer_id}</strong>
            <StatusBadge status={d.status} />
          </div>
          <div className="muted small">
            {d.category?.replace("_", " ") || "—"} · fraud {d.fraud_score ?? "—"} · {d.decision || "—"}
          </div>
        </li>
      ))}
    </ul>
  );
}