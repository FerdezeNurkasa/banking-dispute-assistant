import { useEffect, useState } from "react";
import { api } from "../api.js";

const CATEGORY_LABELS = {
  unauthorized: "Unauthorized",
  duplicate_charge: "Duplicate charge",
  subscription_cancelled: "Subscription cancelled",
  not_received: "Not received",
  wrong_amount: "Wrong amount",
  other: "Other",
};
const AGENT_LABELS = {
  privacy_guard: "Privacy guard",
  intake_agent: "Intake",
  investigator_agent: "Investigator",
  fraud_agent: "Fraud",
  policy_agent: "Policy",
  decision_agent: "Decision",
};

const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const fmtMs = (ms) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`);

function Kpi({ label, value, hint }) {
  return (
    <div className="kpi">
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {hint && <span className="kpi-hint">{hint}</span>}
    </div>
  );
}

/** Card with a chart, a hover tooltip and a "Table" toggle for an accessible view of the same data. */
function ChartCard({ title, subtitle, rows, format = (v) => v, children }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <div className="card chart-card">
      <div className="row">
        <div>
          <h3>{title}</h3>
          {subtitle && <p className="muted small">{subtitle}</p>}
        </div>
        <button className="small-btn" onClick={() => setAsTable(!asTable)}>{asTable ? "Chart" : "Table"}</button>
      </div>
      {asTable ? (
        <table className="data-table">
          <tbody>
            {rows.map((r) => (
              <tr key={r.label}><td>{r.label}</td><td>{format(r.value)}</td></tr>
            ))}
          </tbody>
        </table>
      ) : children}
    </div>
  );
}

/** Horizontal bars: one row per category, value labelled at the end of each bar. */
function HBars({ rows, format = (v) => v, total }) {
  const [hover, setHover] = useState(null);
  const max = Math.max(1, ...rows.map((r) => r.value));
  if (!rows.length) return <p className="muted">No data yet.</p>;
  return (
    <div className="hbars">
      {rows.map((r) => (
        <div key={r.label} className="hbar-row" onMouseEnter={() => setHover(r.label)} onMouseLeave={() => setHover(null)}>
          <span className="hbar-label">
            {r.dot && <span className="dot" style={{ background: r.color }} />}
            {r.label}
          </span>
          <div className="hbar-track">
            <div className="hbar-fill" style={{ width: `${(r.value / max) * 100}%`, background: r.color || "var(--series-1)" }} />
            {hover === r.label && (
              <div className="tooltip">
                <b>{r.label}</b>: {format(r.value)}
                {total ? ` (${Math.round((r.value / total) * 100)}%)` : ""}
              </div>
            )}
          </div>
          <span className="hbar-value">{format(r.value)}</span>
        </div>
      ))}
    </div>
  );
}

/** Vertical columns for a time series (disputes per day). */
function Columns({ rows }) {
  const [hover, setHover] = useState(null);
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="columns">
      <div className="columns-plot">
        {rows.map((r, i) => (
          <div key={r.label} className="col" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            {hover === i && <div className="tooltip col-tip"><b>{r.label}</b>: {r.value} disputes</div>}
            <div className="col-fill" style={{ height: `${(r.value / max) * 100}%` }} />
          </div>
        ))}
      </div>
      <div className="columns-axis">
        {rows.map((r, i) => (
          <span key={r.label}>{i % 3 === 0 || i === rows.length - 1 ? r.short : ""}</span>
        ))}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = () => api.analytics().then(setData).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  if (error) return <div className="card error">{error}</div>;
  if (!data) return <div className="card">Loading analytics…</div>;

  const k = data.kpis;
  const processed = data.routing.auto_resolved + data.routing.human_reviewed + data.routing.waiting_for_review + data.routing.failed;
  const routing = [
    { label: "Resolved by agents", value: data.routing.auto_resolved },
    { label: "Resolved by a reviewer", value: data.routing.human_reviewed },
    { label: "Waiting for review", value: data.routing.waiting_for_review },
    { label: "Failed", value: data.routing.failed },
  ];
  const categories = Object.entries(data.by_category)
    .map(([key, value]) => ({ label: CATEGORY_LABELS[key] || key, value }))
    .sort((a, b) => b.value - a.value);
  const fraudTotal = data.fraud_risk.low + data.fraud_risk.medium + data.fraud_risk.high;
  const risk = [
    { label: "Low (0–39)", value: data.fraud_risk.low, color: "var(--status-good)", dot: true },
    { label: "Medium (40–69)", value: data.fraud_risk.medium, color: "var(--status-warning)", dot: true },
    { label: "High (70–100)", value: data.fraud_risk.high, color: "var(--status-critical)", dot: true },
  ];
  const latency = Object.entries(data.agent_latency_ms).map(([key, value]) => ({ label: AGENT_LABELS[key] || key, value }));
  const daily = data.daily.map((d) => {
    const date = new Date(`${d.date}T00:00:00`);
    return { label: date.toLocaleDateString(undefined, { day: "numeric", month: "short" }),
             short: date.toLocaleDateString(undefined, { day: "numeric", month: "numeric" }), value: d.count };
  });

  return (
    <div className="dashboard">
      <div className="row">
        <h2>Analytics</h2>
        <button className="small-btn" onClick={load}>Refresh</button>
      </div>

      <div className="kpis">
        <Kpi label="Total disputes" value={k.total_disputes} />
        <Kpi label="Automation rate" value={pct(k.automation_rate)} hint="resolved without a human" />
        <Kpi label="Waiting for review" value={k.pending_review} />
        <Kpi label="Human override rate" value={pct(k.human_override_rate)} hint="reviewer disagreed with agents" />
        <Kpi label="Average fraud score" value={k.avg_fraud_score ?? "—"} />
        <Kpi label="Refunded" value={`${Math.round(k.refunded_eur).toLocaleString()} EUR`} />
        <Kpi label="Avg. workflow time" value={k.avg_workflow_ms == null ? "—" : fmtMs(k.avg_workflow_ms)} hint="all agents, end to end" />
      </div>

      <div className="chart-grid">
        <ChartCard title="How disputes were handled" rows={routing}>
          <HBars rows={routing} total={processed} />
        </ChartCard>
        <ChartCard title="Disputes by category" rows={categories}>
          <HBars rows={categories} total={categories.reduce((s, r) => s + r.value, 0)} />
        </ChartCard>
        <ChartCard title="Fraud risk" subtitle="Fraud score of each processed dispute" rows={risk}>
          <HBars rows={risk} total={fraudTotal} />
        </ChartCard>
        <ChartCard title="Average time per agent" subtitle="Includes the LLM call" rows={latency} format={fmtMs}>
          <HBars rows={latency} format={fmtMs} />
        </ChartCard>
        <ChartCard title="Disputes per day" subtitle="Last 14 days" rows={daily}>
          <Columns rows={daily} />
        </ChartCard>
      </div>
    </div>
  );
}