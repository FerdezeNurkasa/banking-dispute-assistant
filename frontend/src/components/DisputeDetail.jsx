import { useEffect, useState } from "react";
import { api } from "../api.js";
import { StatusBadge } from "./DisputeList.jsx";

const AGENT_LABELS = {
  system: "System",
  intake_agent: "Intake agent",
  investigator_agent: "Investigator agent",
  fraud_agent: "Fraud agent",
  policy_agent: "Policy agent",
  decision_agent: "Decision agent",
  router: "Router",
};

function FraudMeter({ score }) {
  const level = score >= 70 ? "high" : score >= 40 ? "medium" : "low";
  return (
    <div className="meter">
      <div className={`meter-fill ${level}`} style={{ width: `${score}%` }} />
      <span>{score}/100</span>
    </div>
  );
}

function ReviewPanel({ dispute, onReviewed }) {
  const [reviewer, setReviewer] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  const submit = async (decision) => {
    try {
      setError("");
      onReviewed(await api.review(dispute.id, { reviewer, decision, note }));
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="card review">
      <h3>Human review required</h3>
      <ul>{dispute.result.route_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      <input placeholder="Your name" value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
      <textarea rows={2} placeholder="Note for the audit log" value={note} onChange={(e) => setNote(e.target.value)} />
      {error && <div className="error">{error}</div>}
      <div className="row gap">
        <button className="approve" disabled={reviewer.length < 2} onClick={() => submit("refund")}>Approve refund</button>
        <button className="reject" disabled={reviewer.length < 2} onClick={() => submit("reject")}>Reject</button>
      </div>
    </div>
  );
}

export default function DisputeDetail({ id, onChanged }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setD(null);
    api.dispute(id).then(setD).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <div className="card error">{error}</div>;
  if (!d) return <div className="card">Loading…</div>;
  const r = d.result;

  return (
    <div className="detail">
      <div className="card">
        <div className="row">
          <h2>Dispute #{d.id}</h2>
          <StatusBadge status={d.status} />
        </div>
        <p className="quote">“{d.description}”</p>
        {r && (
          <div className="grid">
            <div><span className="label">Transaction</span>{r.transaction.merchant} · {r.transaction.amount.toFixed(2)} {r.transaction.currency} · {r.transaction.country} · {r.transaction.channel}</div>
            <div><span className="label">Category</span>{r.intake.category.replace("_", " ")}</div>
            <div><span className="label">Fraud score</span><FraudMeter score={r.fraud.fraud_score} /></div>
            <div><span className="label">Policy</span>{r.policy.eligible ? "Eligible" : "Not eligible"} ({r.policy.applied_rules.join(", ")})</div>
            <div><span className="label">Agent decision</span><b>{r.decision.decision}</b> · confidence {(r.decision.confidence * 100).toFixed(0)}%</div>
            <div><span className="label">Final decision</span><b>{d.status === "resolved" ? d.decision : "pending"}</b></div>
          </div>
        )}
      </div>

      {d.status === "needs_review" && r && (
        <ReviewPanel dispute={d} onReviewed={(updated) => { setD(updated); onChanged(); }} />
      )}

      {r && (
        <div className="card">
          <h3>Rationale</h3>
          <p>{r.decision.rationale}</p>
          <h3>Message to customer</h3>
          <p className="quote">{r.decision.customer_message}</p>
          <h3>Evidence</h3>
          <p>{r.evidence.summary}</p>
          {r.fraud.signals.length > 0 && (
            <>
              <h3>Fraud signals</h3>
              <ul>{r.fraud.signals.map((s) => <li key={s}>{s}</li>)}</ul>
            </>
          )}
        </div>
      )}

      <div className="card">
        <h3>Audit trail</h3>
        <ol className="timeline">
          {d.audit_logs.map((a) => (
            <li key={a.id}>
              <div className="row">
                <strong>{AGENT_LABELS[a.actor] || a.actor.replace("human:", "Reviewer: ")}</strong>
                <span className="muted small">
                  {new Date(a.created_at).toLocaleTimeString()}{a.duration_ms != null && ` · ${a.duration_ms} ms`}
                </span>
              </div>
              <div>{a.action}</div>
              {a.details?.evidence?.tool_calls?.length > 0 && (
                <div className="tools">
                  {a.details.evidence.tool_calls.map((t, i) => (
                    <code key={i}>{t.tool}({Object.values(t.args).join(", ")})</code>
                  ))}
                </div>
              )}
              {a.actor.startsWith("human:") && a.details.note && <div className="muted">Note: {a.details.note}</div>}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}