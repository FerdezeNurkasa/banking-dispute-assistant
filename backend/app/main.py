import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import Customer, Dispute, SessionLocal, Transaction, init_db
from app.search import search_disputes
from app.seed import seed
from app.service import human_review, process_dispute

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed()
    yield


app = FastAPI(title="Banking Dispute Assistant", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


def require_api_key(x_api_key: str | None = Header(default=None)):
    """Simple access control. In AWS you can also put an authorizer on API Gateway."""
    expected = os.getenv("API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------- schemas
class DisputeCreate(BaseModel):
    customer_id: str
    transaction_id: str
    description: str = Field(min_length=10, max_length=2000)


class ReviewIn(BaseModel):
    reviewer: str = Field(min_length=2, max_length=40)
    decision: Literal["refund", "reject"]
    note: str = Field(default="", max_length=1000)


class AuditOut(BaseModel):
    id: int
    actor: str
    action: str
    details: dict
    duration_ms: int | None
    created_at: datetime


class DisputeOut(BaseModel):
    id: int
    customer_id: str
    transaction_id: str
    description: str
    status: str
    category: str | None
    fraud_score: int | None
    decision: str | None
    confidence: float | None
    created_at: datetime


class DisputeDetail(DisputeOut):
    result: dict | None
    audit_logs: list[AuditOut]


def _detail(d: Dispute) -> DisputeDetail:
    return DisputeDetail(**{c: getattr(d, c) for c in DisputeOut.model_fields}, result=d.result,
                         audit_logs=[AuditOut(**{c: getattr(a, c) for c in AuditOut.model_fields})
                                     for a in d.audit_logs])


def _load(dispute_id: int) -> Dispute:
    with SessionLocal() as db:
        d = db.scalar(select(Dispute).options(selectinload(Dispute.audit_logs)).where(Dispute.id == dispute_id))
        if not d:
            raise HTTPException(404, "Dispute not found")
        return d


# ---------------------------------------------------------------- routes
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/customers", dependencies=[Depends(require_api_key)])
def list_customers():
    with SessionLocal() as db:
        customers = db.scalars(select(Customer).options(selectinload(Customer.transactions))).all()
        return [{
            "id": c.id, "name": c.name,
            "transactions": [{"id": t.id, "merchant": t.merchant, "amount": t.amount, "currency": t.currency,
                              "created_at": t.created_at}
                             for t in sorted(c.transactions, key=lambda t: t.created_at, reverse=True)],
        } for c in customers]


@app.post("/disputes", response_model=DisputeDetail, status_code=201, dependencies=[Depends(require_api_key)])
def create_dispute(body: DisputeCreate):
    with SessionLocal() as db:
        tx = db.get(Transaction, body.transaction_id)
        if not tx or tx.customer_id != body.customer_id:
            raise HTTPException(400, "Transaction does not belong to this customer")
        dispute = Dispute(**body.model_dump(), status="processing")
        db.add(dispute)
        db.commit()
        dispute_id = dispute.id
    process_dispute(dispute_id)  # synchronous; see README for the async (SQS) version
    return _detail(_load(dispute_id))


@app.get("/disputes", response_model=list[DisputeOut], dependencies=[Depends(require_api_key)])
def list_disputes(status: str | None = None):
    with SessionLocal() as db:
        q = select(Dispute).order_by(Dispute.id.desc())
        if status:
            q = q.where(Dispute.status == status)
        return [DisputeOut(**{c: getattr(d, c) for c in DisputeOut.model_fields}) for d in db.scalars(q)]


@app.get("/disputes/{dispute_id}", response_model=DisputeDetail, dependencies=[Depends(require_api_key)])
def get_dispute(dispute_id: int):
    return _detail(_load(dispute_id))


@app.post("/disputes/{dispute_id}/review", response_model=DisputeDetail, dependencies=[Depends(require_api_key)])
def review_dispute(dispute_id: int, body: ReviewIn):
    if _load(dispute_id).status != "needs_review":
        raise HTTPException(409, "Only disputes waiting for review can be reviewed")
    human_review(dispute_id, body.reviewer, body.decision, body.note)
    return _detail(_load(dispute_id))


@app.get("/search", response_model=list[DisputeOut], dependencies=[Depends(require_api_key)])
def search(q: str):
    ids = search_disputes(q)
    with SessionLocal() as db:
        found = {d.id: d for d in db.scalars(select(Dispute).where(Dispute.id.in_(ids)))}
        return [DisputeOut(**{c: getattr(found[i], c) for c in DisputeOut.model_fields}) for i in ids if i in found]