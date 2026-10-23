"""Demo data: bank employees (users) and three customers, each set up for a different dispute scenario."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import settings
from app.db import Customer, SessionLocal, Transaction, User
from app.security import hash_password

DEMO_USERS = [
    ("arta", "Arta Gashi", "agent"),     # submits disputes for customers
    ("ana", "Ana Morina", "reviewer"),   # approves or rejects risky disputes
    ("leon", "Leon Shala", "reviewer"),  # second reviewer, so the four-eyes rule can be demonstrated
]


def seed():
    seed_users()
    seed_customers()


def seed_users():
    with SessionLocal() as db:
        if db.scalar(select(User).limit(1)):
            return
        db.add_all([User(username=u, full_name=n, role=r, password_hash=hash_password(settings.DEMO_PASSWORD))
                    for u, n, r in DEMO_USERS])
        db.commit()


def seed_customers():
    with SessionLocal() as db:
        if db.scalar(select(Customer).limit(1)):
            return
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        d = lambda days, hour=14, minute=0: (now - timedelta(days=days)).replace(hour=hour, minute=minute)

        db.add_all([
            Customer(id="C001", name="Arben Krasniqi", home_country="XK"),
            Customer(id="C002", name="Drita Berisha", home_country="XK"),
            Customer(id="C003", name="Blerim Hoxha", home_country="XK"),
        ])
        db.add_all([
            # C001 - scenario: duplicate charge at the supermarket
            Transaction(id="T1001", customer_id="C001", merchant="Viva Fresh", amount=23.40, country="XK", channel="card_present", created_at=d(5, 18, 2)),
            Transaction(id="T1002", customer_id="C001", merchant="Viva Fresh", amount=23.40, country="XK", channel="card_present", created_at=d(5, 18, 3)),
            Transaction(id="T1003", customer_id="C001", merchant="Shell Prishtina", amount=45.00, country="XK", channel="card_present", created_at=d(9)),
            Transaction(id="T1004", customer_id="C001", merchant="Albi Mall", amount=62.90, country="XK", channel="card_present", created_at=d(15)),
            Transaction(id="T1005", customer_id="C001", merchant="Viva Fresh", amount=31.15, country="XK", channel="card_present", created_at=d(20)),

            # C002 - scenario: unauthorized, high-risk online purchase abroad at night
            Transaction(id="T2001", customer_id="C002", merchant="ElectroWorld Lagos", amount=1450.00, country="NG", channel="online", created_at=d(2, 3, 17)),
            Transaction(id="T2002", customer_id="C002", merchant="Interex", amount=28.70, country="XK", channel="card_present", created_at=d(4)),
            Transaction(id="T2003", customer_id="C002", merchant="Bolt", amount=4.50, country="XK", channel="online", created_at=d(6)),
            Transaction(id="T2004", customer_id="C002", merchant="Interex", amount=35.20, country="XK", channel="card_present", created_at=d(11)),
            Transaction(id="T2005", customer_id="C002", merchant="Café Dit' e Nat'", amount=7.00, country="XK", channel="card_present", created_at=d(13)),

            # C003 - scenario: subscription charged after cancellation
            Transaction(id="T3001", customer_id="C003", merchant="StreamPlus", amount=12.99, country="IE", channel="online", created_at=d(3)),
            Transaction(id="T3002", customer_id="C003", merchant="StreamPlus", amount=12.99, country="IE", channel="online", created_at=d(33)),
            Transaction(id="T3003", customer_id="C003", merchant="StreamPlus", amount=12.99, country="IE", channel="online", created_at=d(63)),
            Transaction(id="T3004", customer_id="C003", merchant="Meridian Express", amount=18.50, country="XK", channel="card_present", created_at=d(8)),
        ])
        db.commit()