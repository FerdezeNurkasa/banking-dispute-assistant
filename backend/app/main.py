import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.analytics import compute_analytics
from app.config import settings
from app.db import AuditLog, Customer, Dispute, SessionLocal, Transaction, init_db
from app.search import search_disputes
from app.security import CurrentUser, authenticate, create_access_token, get_current_user, require_role
from app.seed import seed
from app.service import human_review, process_dispute

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed()
    yield


app = FastAPI(title="Banking Dispute Assistant", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_methods=["*"],
                   allow_headers=["Authorization", "Content-Type"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"  # responses contain customer data: never cache
    return response


# ---------------------------------------------------------------- schemas
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: CurrentUser


class DisputeCreate(BaseModel):
    customer_id: str
    transaction_id: str
    description: str = Field(min_length=10, max_length=2000)


class ReviewIn(BaseModel):
    # No "reviewer" field: the reviewer is ALWAYS the logged-in user, so nobody can act in someone else's name
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
    created_by: str | None
    status: str
    category: str | None
    fraud_score: int | None
    decision: str | None
    confidence: float | None
    created_at: datetime


class DisputeDetail(DisputeOut):
    result: dict | None
    audit_logs: list[AuditOut]


def _out(d: Dispute) -> DisputeOut:
    return DisputeOut(**{c: getattr(d, c) for c in DisputeOut.model_fields})


def _detail(d: Dispute) -> DisputeDetail:
    return DisputeDetail(**_out(d).model_dump(), result=d.result,
                         audit_logs=[AuditOut(**{c: getattr(a, c) for c in AuditOut.model_fields})
                                     for a in d.audit_logs])


def _load(dispute_id: int) -> Dispute:
    with SessionLocal() as db:
        d = db.scalar(select(Dispute).options(selectinload(Dispute.audit_logs)).where(Dispute.id == dispute_id))
        if not d:
            raise HTTPException(404, "Dispute not found")
        return d


# ---------------------------------------------------------------- public routes
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/login", response_model=LoginOut)
def login(body: LoginIn):
    user = authenticate(body.username, body.password)
    return LoginOut(access_token=create_access_token(user),
                    user=CurrentUser(username=user.username, full_name=user.full_name, role=user.role))


# ---------------------------------------------------------------- routes for any logged-in employee
@app.get("/auth/me", response_model=CurrentUser)
def me(user: CurrentUser = Depends(get_current_user)):
    return user


@app.get("/customers")
def list_customers(_: CurrentUser = Depends(get_current_user)):
    with SessionLocal() as db:
        customers = db.scalars(select(Customer).options(selectinload(Customer.transactions))).all()
        return [{
            "id": c.id, "name": c.name,
            "transactions": [{"id": t.id, "merchant": t.merchant, "amount": t.amount, "currency": t.currency,
                              "created_at": t.created_at}
                             for t in sorted(c.transactions, key=lambda t: t.created_at, reverse=True)],
        } for c in customers]


@app.post("/disputes", response_model=DisputeDetail, status_code=201)
def create_dispute(body: DisputeCreate, user: CurrentUser = Depends(get_current_user)):
    with SessionLocal() as db:
        tx = db.get(Transaction, body.transaction_id)
        if not tx or tx.customer_id != body.customer_id:
            raise HTTPException(400, "Transaction does not belong to this customer")
        dispute = Dispute(**body.model_dump(), created_by=user.username, status="processing")
        db.add(dispute)
        db.flush()
        db.add(AuditLog(dispute_id=dispute.id, actor=f"user:{user.username}", action="Submitted dispute",
                        details={"role": user.role}))
        db.commit()
        dispute_id = dispute.id
    process_dispute(dispute_id)  # synchronous; see README for the async (SQS) version
    return _detail(_load(dispute_id))


@app.get("/disputes", response_model=list[DisputeOut])
def list_disputes(status: str | None = None, _: CurrentUser = Depends(get_current_user)):
    with SessionLocal() as db:
        q = select(Dispute).order_by(Dispute.id.desc())
        if status:
            q = q.where(Dispute.status == status)
        return [_out(d) for d in db.scalars(q)]


@app.get("/disputes/{dispute_id}", response_model=DisputeDetail)
def get_dispute(dispute_id: int, _: CurrentUser = Depends(get_current_user)):
    return _detail(_load(dispute_id))


@app.get("/search", response_model=list[DisputeOut])
def search(q: str, _: CurrentUser = Depends(get_current_user)):
    ids = search_disputes(q)
    with SessionLocal() as db:
        found = {d.id: d for d in db.scalars(select(Dispute).where(Dispute.id.in_(ids)))}
        return [_out(found[i]) for i in ids if i in found]


@app.get("/analytics")
def analytics(days: int = 14, _: CurrentUser = Depends(get_current_user)):
    return compute_analytics(days=max(1, min(days, 90)))


# ---------------------------------------------------------------- reviewer-only routes
@app.post("/disputes/{dispute_id}/review", response_model=DisputeDetail)
def review_dispute(dispute_id: int, body: ReviewIn, user: CurrentUser = Depends(require_role("reviewer"))):
    dispute = _load(dispute_id)
    if dispute.status != "needs_review":
        raise HTTPException(409, "Only disputes waiting for review can be reviewed")
    if dispute.created_by == user.username:
        # Four-eyes principle: the person who submitted a case can never approve it
        raise HTTPException(403, "Four-eyes rule: you cannot review a dispute you submitted yourself")
    human_review(dispute_id, user.username, body.decision, body.note)
    return _detail(_load(dispute_id))