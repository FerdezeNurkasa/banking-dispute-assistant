"""Tools the investigator agent can call. Each one is a normal Python function that reads the database."""
from datetime import timedelta

from langchain_core.tools import tool
from sqlalchemy import select

from app.db import Customer, SessionLocal, Transaction


def _tx_dict(t: Transaction) -> dict:
    return {
        "id": t.id, "merchant": t.merchant, "amount": t.amount, "currency": t.currency,
        "country": t.country, "channel": t.channel, "created_at": t.created_at.isoformat(),
    }


@tool
def get_transaction(transaction_id: str) -> dict:
    """Get the details of one card transaction by its ID."""
    with SessionLocal() as db:
        t = db.get(Transaction, transaction_id)
        return _tx_dict(t) if t else {"error": f"Transaction {transaction_id} not found"}


@tool
def get_customer_history(customer_id: str, limit: int = 30) -> dict:
    """Get the customer's profile and their most recent transactions."""
    with SessionLocal() as db:
        c = db.get(Customer, customer_id)
        if not c:
            return {"error": f"Customer {customer_id} not found"}
        txs = db.scalars(
            select(Transaction).where(Transaction.customer_id == customer_id)
            .order_by(Transaction.created_at.desc()).limit(limit)
        ).all()
        return {
            "customer": {"id": c.id, "name": c.name, "home_country": c.home_country},
            "transactions": [_tx_dict(t) for t in txs],
        }


@tool
def find_similar_charges(transaction_id: str, window_days: int = 3) -> dict:
    """Find other charges from the same merchant with the same amount close in time (possible duplicates)."""
    with SessionLocal() as db:
        t = db.get(Transaction, transaction_id)
        if not t:
            return {"error": f"Transaction {transaction_id} not found"}
        window = timedelta(days=window_days)
        similar = db.scalars(
            select(Transaction).where(
                Transaction.customer_id == t.customer_id,
                Transaction.merchant == t.merchant,
                Transaction.amount == t.amount,
                Transaction.id != t.id,
                Transaction.created_at.between(t.created_at - window, t.created_at + window),
            )
        ).all()
        return {"similar_charges": [_tx_dict(s) for s in similar], "count": len(similar)}


@tool
def get_merchant_history(customer_id: str, merchant: str) -> dict:
    """Get all previous transactions of this customer at a given merchant (e.g. recurring subscriptions)."""
    with SessionLocal() as db:
        txs = db.scalars(
            select(Transaction).where(Transaction.customer_id == customer_id, Transaction.merchant == merchant)
            .order_by(Transaction.created_at)
        ).all()
        return {"merchant": merchant, "transactions": [_tx_dict(t) for t in txs], "count": len(txs)}


INVESTIGATOR_TOOLS = [get_transaction, get_customer_history, find_similar_charges, get_merchant_history]
TOOLS_BY_NAME = {t.name: t for t in INVESTIGATOR_TOOLS}