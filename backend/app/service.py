"""Runs the agent workflow for a dispute and persists the result + audit trail."""
import logging
from datetime import datetime

from app.agents.graph import dispute_graph
from app.db import AuditLog, Dispute, SessionLocal
from app.search import index_dispute

log = logging.getLogger(__name__)


def process_dispute(dispute_id: int) -> Dispute:
    with SessionLocal() as db:
        dispute = db.get(Dispute, dispute_id)
        db.add(AuditLog(dispute_id=dispute.id, actor="system", action="Started agent workflow", details={}))
        db.commit()

        try:
            state = dispute_graph.invoke({
                "dispute_id": dispute.id, "customer_id": dispute.customer_id,
                "transaction_id": dispute.transaction_id, "description": dispute.description, "audit": [],
            })
        except Exception as exc:
            log.exception("Workflow failed for dispute %s", dispute.id)
            dispute.status = "failed"
            db.add(AuditLog(dispute_id=dispute.id, actor="system", action="Workflow failed",
                            details={"error": str(exc)[:500]}))
            db.commit()
            return dispute

        for entry in state["audit"]:
            db.add(AuditLog(dispute_id=dispute.id, actor=entry["actor"], action=entry["action"],
                            details=entry["details"], duration_ms=entry["duration_ms"],
                            created_at=datetime.fromisoformat(entry["at"])))

        dispute.category = state["intake"]["category"]
        dispute.fraud_score = state["fraud"]["fraud_score"]
        dispute.decision = state["decision"]["decision"]
        dispute.confidence = state["decision"]["confidence"]
        dispute.status = "needs_review" if state["route"] == "needs_review" else "resolved"
        dispute.result = {k: state[k] for k in
                          ("transaction", "intake", "evidence", "fraud", "policy", "decision", "route", "route_reasons")}
        db.commit()
        db.refresh(dispute)
        index_dispute(dispute)
        return dispute


def human_review(dispute_id: int, reviewer: str, decision: str, note: str) -> Dispute:
    with SessionLocal() as db:
        dispute = db.get(Dispute, dispute_id)
        previous = dispute.decision
        dispute.decision = decision
        dispute.status = "resolved"
        db.add(AuditLog(dispute_id=dispute.id, actor=f"human:{reviewer}", action="Human review decision",
                        details={"decision": decision, "agent_suggestion": previous, "note": note}))
        db.commit()
        db.refresh(dispute)
        index_dispute(dispute)
        return dispute