"""Full-text search over disputes. Uses OpenSearch when OPENSEARCH_URL is set, otherwise the database."""
import logging

from sqlalchemy import or_, select

from app.config import settings
from app.db import Dispute, SessionLocal

log = logging.getLogger(__name__)
_client = None


def _os():
    global _client
    if _client is None and settings.OPENSEARCH_URL:
        from opensearchpy import OpenSearch
        _client = OpenSearch(settings.OPENSEARCH_URL, timeout=5)
        if not _client.indices.exists(index=settings.OPENSEARCH_INDEX):
            _client.indices.create(index=settings.OPENSEARCH_INDEX, body={"mappings": {"properties": {
                "description": {"type": "text"}, "summary": {"type": "text"}, "rationale": {"type": "text"},
                "merchant": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
                "category": {"type": "keyword"}, "status": {"type": "keyword"},
                "decision": {"type": "keyword"}, "customer_id": {"type": "keyword"},
                "fraud_score": {"type": "integer"}, "created_at": {"type": "date"},
            }}})
    return _client


def index_dispute(d: Dispute) -> None:
    client = _os()
    if not client:
        return
    r = d.result or {}
    try:
        client.index(index=settings.OPENSEARCH_INDEX, id=str(d.id), refresh=True, body={
            "description": d.description, "summary": r.get("intake", {}).get("summary"),
            "rationale": r.get("decision", {}).get("rationale"),
            "merchant": r.get("transaction", {}).get("merchant"), "category": d.category,
            "status": d.status, "decision": d.decision, "customer_id": d.customer_id,
            "fraud_score": d.fraud_score, "created_at": d.created_at.isoformat(),
        })
    except Exception:  # search must never break the main workflow
        log.exception("Failed to index dispute %s", d.id)


def search_disputes(q: str, limit: int = 20) -> list[int]:
    """Returns matching dispute IDs, best match first."""
    client = _os()
    if client:
        res = client.search(index=settings.OPENSEARCH_INDEX, body={"size": limit, "query": {"multi_match": {
            "query": q, "fields": ["description^2", "summary", "rationale", "merchant^3", "category"],
            "fuzziness": "AUTO",
        }}})
        return [int(h["_id"]) for h in res["hits"]["hits"]]
    with SessionLocal() as db:
        like = f"%{q}%"
        return list(db.scalars(select(Dispute.id).where(or_(
            Dispute.description.ilike(like), Dispute.category.ilike(like), Dispute.customer_id.ilike(like)
        )).order_by(Dispute.id.desc()).limit(limit)))