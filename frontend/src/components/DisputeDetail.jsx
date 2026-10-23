import { useEffect, useState } from "react";
import { api } from "../api.js";
import { StatusBadge } from "./DisputeList.jsx";

const AGENT_LABELS = {
  system: "System",
  privacy_guard: "Privacy guard",
  intake_agent: "Intake agent",
  investigator_agent: "Investigator agent",
  fraud_agent: "Fraud agent",
  policy_agent: "Policy agent",
  decision_agent: "Decision agent",
  router: "Router",
};

const PII_LABELS = { CARD_NUMBER: "card number", IBAN: "IBAN", EMAIL: "email", PHONE: "phone number", NAME: "name" };

function actorLabel(actor) {
  if (AGENT_LABELS[actor]) return AGENT_LABELS[actor];
  if (actor.startsWith("human:")) return `Reviewer: ${actor.slice(6)}`;
  if (actor.startsWith("user:")) return `Employee: ${actor.slice(5)}`;
  return actor;
}

function FraudMeter({ score }) {
  const level = score >= 70 ? "high" : score >= 40 ? "medium" : "low";
  return (
    <div className="meter">
      <div className={`meter-fill ${level}`} style={{ width: `${score}%` }} />
      <span>{score}/100 · {level}</span>
    </div>
  );
}

function PrivacyNote({ privacy }) {
  if (!privacy) return null;
  const items = Object.entries(privacy.redactions);
  return (
    <div className="privacy-note">
      🔒 {items.length === 0
        ? "No personal data found in the complaint."
        : `Masked before AI processing: ${items.map(([k, n]) => `${n} ${PII_LABELS[k] || k}${n > 1 ? "s" : ""}`).join(", ")}.`}
    </div>
  );
}

function ReviewPanel({ dispute, user, onReviewed }) {
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const reasons = (
    <ul>{dispute.result.route_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
  );

  if (user.role !== "reviewer") {
    return (
      <div className="card review">
        <h3>Waiting for a reviewer</h3>
        {reasons}
        <p className="muted">Only employees with the reviewer role can approve or reject this dispute.</p>
      </div>
    );
  }
  if (dispute.created_by === user.username) {
    return (
      <div className="card review">
        <h3>Waiting for another reviewer</h3>
        {reasons}
        <p className="muted">Four-eyes rule: you submitted this dispute, so a different reviewer must decide.</p>
      </div>
    );
  }

  const submit = async (decision) => {
    setSaving(true);
    try {
      setError("");
      onReviewed(await api.review(dispute.id, { decision, note }));
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card review">
      <h3>Human review required</h3>
      {reasons}
      <textarea rows={2} placeholder="Note for the audit log" value={note} onChange={(e) => setNote(e.target.value)} />
      {error && <div className="error">{error}</div>}
      <div className="row gap">
        <button className="approve" disabled={saving} onClick={() => submit("refund")}>Approve refund</button>
        <button className="reject" disabled={saving} onClick={() => submit("reject")}>Reject</button>
        <span className="muted small">Signed as {user.full_name}</span>
      </div>
    </div>
  );
}

export default function DisputeDetail({ id, user, onChanged }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setD(null);
    setError("");
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
        <p className="muted small">Submitted by {d.created_by || "—"} · {new Date(d.created_at).toLocaleString()}</p>
        {r && <PrivacyNote privacy={r.privacy} />}
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
        <ReviewPanel dispute={d} user={user} onReviewed={(updated) => { setD(updated); onChanged(); }} />
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
            <li key={a.id} className={a.actor.startsWith("human:") || a.actor.startsWith("user:") ? "person" : ""}>
              <div className="row">
                <strong>{actorLabel(a.actor)}</strong>
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
              {a.actor.startsWith("human:") && (
                <div className="muted">
                  Decision: <b>{a.details.decision}</b> (agent suggested {a.details.agent_suggestion})
                  {a.details.note && <> · Note: {a.details.note}</>}
                </div>
              )}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}