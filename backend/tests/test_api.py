import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal, User
from app.main import app
from app.security import hash_password

DISPUTE_C002 = {"customer_id": "C002", "transaction_id": "T2001",
                "description": "I did not buy anything from ElectroWorld Lagos, my card 4111 1111 1111 1111 is with me."}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def login(client, username, password=None):
    r = client.post("/auth/login", json={"username": username, "password": password or settings.DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------- authentication
def test_health_is_public_and_has_security_headers(client):
    r = client.get("/health")
    assert r.json() == {"status": "ok"}
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Cache-Control"] == "no-store"


def test_endpoints_require_login(client):
    for path in ["/customers", "/disputes", "/analytics", "/auth/me"]:
        assert client.get(path).status_code == 401
    assert client.get("/disputes", headers={"Authorization": "Bearer not-a-real-token"}).status_code == 401


def test_login_returns_user_and_role(client):
    r = client.post("/auth/login", json={"username": "ana", "password": settings.DEMO_PASSWORD})
    assert r.json()["user"] == {"username": "ana", "full_name": "Ana Morina", "role": "reviewer"}
    assert client.get("/auth/me", headers=login(client, "ana")).json()["username"] == "ana"


def test_wrong_password_and_unknown_user_give_same_error(client):
    wrong = client.post("/auth/login", json={"username": "ana", "password": "nope"})
    unknown = client.post("/auth/login", json={"username": "nobody", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_account_locks_after_too_many_failed_logins(client):
    with SessionLocal() as db:
        db.add(User(username="lockme", full_name="Lock Test", role="agent", password_hash=hash_password("Right!123")))
        db.commit()
    for _ in range(settings.MAX_FAILED_LOGINS):
        assert client.post("/auth/login", json={"username": "lockme", "password": "wrong"}).status_code == 401
    # even the correct password is refused while locked
    assert client.post("/auth/login", json={"username": "lockme", "password": "Right!123"}).status_code == 423


def test_deactivated_user_loses_access_immediately(client):
    with SessionLocal() as db:
        db.add(User(username="leaver", full_name="Left Company", role="agent", password_hash=hash_password("Bye!1234")))
        db.commit()
    headers = login(client, "leaver", "Bye!1234")
    assert client.get("/disputes", headers=headers).status_code == 200
    with SessionLocal() as db:
        db.get(User, "leaver").is_active = False
        db.commit()
    assert client.get("/disputes", headers=headers).status_code == 401  # same token, now refused


# ---------------------------------------------------------------- disputes, roles and four-eyes
def test_cannot_dispute_someone_elses_transaction(client, fake_llm):
    fake_llm()
    r = client.post("/disputes", headers=login(client, "arta"),
                    json={"customer_id": "C001", "transaction_id": "T2001", "description": "This is not my transaction."})
    assert r.status_code == 400


def test_full_flow_agent_submits_reviewer_approves(client, fake_llm):
    fake_llm(category="unauthorized", fraud=90, decision="refund", confidence=0.9)
    arta, ana = login(client, "arta"), login(client, "ana")

    dispute = client.post("/disputes", headers=arta, json=DISPUTE_C002).json()
    assert dispute["status"] == "needs_review"
    assert dispute["created_by"] == "arta"
    assert dispute["audit_logs"][0]["actor"] == "user:arta"
    assert dispute["result"]["privacy"]["redactions"] == {"CARD_NUMBER": 1}
    # the customer message is personalised again only after the LLM is done
    assert dispute["result"]["decision"]["customer_message"].startswith("Dear Drita,")

    # an agent may not approve refunds
    r = client.post(f"/disputes/{dispute['id']}/review", headers=arta, json={"decision": "refund"})
    assert r.status_code == 403

    r = client.post(f"/disputes/{dispute['id']}/review", headers=ana,
                    json={"decision": "refund", "note": "Confirmed with customer by phone."})
    assert r.status_code == 200
    reviewed = r.json()
    assert reviewed["status"] == "resolved"
    assert reviewed["audit_logs"][-1]["actor"] == "human:ana"  # identity comes from the token

    assert client.post(f"/disputes/{dispute['id']}/review", headers=ana, json={"decision": "reject"}).status_code == 409
    assert any(d["id"] == dispute["id"] for d in client.get("/search", headers=ana, params={"q": "ElectroWorld"}).json())


def test_four_eyes_rule(client, fake_llm):
    fake_llm(category="unauthorized", fraud=90, decision="refund", confidence=0.9)
    ana, leon = login(client, "ana"), login(client, "leon")

    dispute = client.post("/disputes", headers=ana, json=DISPUTE_C002).json()
    r = client.post(f"/disputes/{dispute['id']}/review", headers=ana, json={"decision": "refund"})
    assert r.status_code == 403
    assert "Four-eyes" in r.json()["detail"]
    # a different reviewer can, and here overrides the agent's suggestion
    assert client.post(f"/disputes/{dispute['id']}/review", headers=leon, json={"decision": "reject"}).status_code == 200


# ---------------------------------------------------------------- analytics
def test_analytics(client, fake_llm):
    headers, ana = login(client, "arta"), login(client, "ana")
    # one dispute the agents resolve alone...
    fake_llm(category="duplicate_charge", fraud=5, decision="refund", confidence=0.95)
    client.post("/disputes", headers=headers, json={"customer_id": "C001", "transaction_id": "T1002",
                                                    "description": "I was charged twice at Viva Fresh."})
    # ...and one that a human reviews
    fake_llm(category="unauthorized", fraud=90, decision="refund", confidence=0.9)
    risky = client.post("/disputes", headers=headers, json=DISPUTE_C002).json()
    client.post(f"/disputes/{risky['id']}/review", headers=ana, json={"decision": "refund"})

    data = client.get("/analytics", headers=headers).json()

    k = data["kpis"]
    assert k["total_disputes"] >= 2
    assert 0 < k["automation_rate"] < 1  # some auto-resolved, some sent to humans
    assert k["human_override_rate"] is not None
    assert k["refunded_eur"] >= 23.40
    assert data["by_category"]["duplicate_charge"] >= 1
    assert data["routing"]["auto_resolved"] >= 1 and data["routing"]["human_reviewed"] >= 1
    assert set(data["fraud_risk"]) == {"low", "medium", "high"}
    assert "privacy_guard" in data["agent_latency_ms"]
    assert len(data["daily"]) == 14 and data["daily"][-1]["count"] >= 1