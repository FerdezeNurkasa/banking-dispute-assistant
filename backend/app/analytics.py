"""KPIs for the analytics dashboard: how much the agents automate, how risky the cases are, how fast it runs."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.db import AuditLog, Dispute, SessionLocal

AGENTS = ["privacy_guard", "intake_agent", "investigator_agent", "fraud_agent", "policy_agent", "decision_agent"]


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute_analytics(days: int = 14) -> dict:
    with SessionLocal() as db:
        # Simple counts are done by the database with GROUP BY
        by_status = dict(db.execute(select(Dispute.status, func.count()).group_by(Dispute.status)).all())
        by_category = dict(db.execute(
            select(Dispute.category, func.count()).where(Dispute.category.is_not(None)).group_by(Dispute.category)
        ).all())
        agent_latency = dict(db.execute(
            select(AuditLog.actor, func.avg(AuditLog.duration_ms))
            .where(AuditLog.actor.in_(AGENTS)).group_by(AuditLog.actor)
        ).all())

        disputes = db.scalars(select(Dispute)).all()
        logs = db.scalars(select(AuditLog).where(AuditLog.actor.in_(["system", "router"]))).all()

    processed = [d for d in disputes if d.result]
    auto_resolved = [d for d in processed if d.result.get("route") == "auto_resolved"]
    sent_to_review = [d for d in processed if d.result.get("route") == "needs_review"]
    reviewed = [d for d in sent_to_review if d.status == "resolved"]

    # Override = the human chose a different outcome than the agent suggested (refund/reject only)
    comparable = [d for d in reviewed if d.result["decision"]["decision"] in ("refund", "reject")]
    overrides = [d for d in comparable if d.decision != d.result["decision"]["decision"]]

    final_decisions = Counter(d.decision for d in disputes if d.status == "resolved")
    refunded_eur = sum(d.result["transaction"]["amount"] for d in disputes
                       if d.status == "resolved" and d.decision == "refund" and d.result)

    fraud_scores = [d.fraud_score for d in processed if d.fraud_score is not None]
    fraud_buckets = {
        "low": sum(1 for s in fraud_scores if s < 40),
        "medium": sum(1 for s in fraud_scores if 40 <= s < 70),
        "high": sum(1 for s in fraud_scores if s >= 70),
    }

    # End-to-end workflow time = router finished - workflow started (per dispute)
    starts, ends = {}, {}
    for log in logs:
        if log.actor == "system" and log.action == "Started agent workflow":
            starts[log.dispute_id] = _aware(log.created_at)
        elif log.actor == "router":
            ends[log.dispute_id] = _aware(log.created_at)
    durations = [(ends[i] - starts[i]).total_seconds() * 1000 for i in ends if i in starts]

    # Disputes per day for the last N days (including days with zero)
    today = datetime.now(timezone.utc).date()
    per_day = defaultdict(int)
    for d in disputes:
        per_day[_aware(d.created_at).date()] += 1
    daily = [{"date": (today - timedelta(days=i)).isoformat(), "count": per_day[today - timedelta(days=i)]}
             for i in range(days - 1, -1, -1)]

    rate = lambda part, whole: round(len(part) / len(whole), 3) if whole else None
    return {
        "kpis": {
            "total_disputes": len(disputes),
            "automation_rate": rate(auto_resolved, processed),
            "pending_review": by_status.get("needs_review", 0),
            "avg_fraud_score": round(sum(fraud_scores) / len(fraud_scores), 1) if fraud_scores else None,
            "human_override_rate": rate(overrides, comparable),
            "refunded_eur": round(refunded_eur, 2),
            "avg_workflow_ms": round(sum(durations) / len(durations)) if durations else None,
        },
        "by_status": by_status,
        "by_category": by_category,
        "final_decisions": dict(final_decisions),
        "routing": {"auto_resolved": len(auto_resolved), "human_reviewed": len(reviewed),
                    "waiting_for_review": by_status.get("needs_review", 0), "failed": by_status.get("failed", 0)},
        "fraud_risk": fraud_buckets,
        "agent_latency_ms": {a: round(float(agent_latency[a])) for a in AGENTS if agent_latency.get(a) is not None},
        "daily": daily,
    }