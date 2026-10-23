import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_customers_have_transactions(client):
    customers = client.get("/customers").json()
    assert {c["id"] for c in customers} >= {"C001", "C002", "C003"}


def test_cannot_dispute_someone_elses_transaction(client, fake_llm):
    fake_llm()
    r = client.post("/disputes", json={"customer_id": "C001", "transaction_id": "T2001",
                                       "description": "This is not my transaction at all."})
    assert r.status_code == 400


def test_full_flow_with_human_review(client, fake_llm):
    fake_llm(category="unauthorized", fraud=90, decision="refund", confidence=0.9)
    r = client.post("/disputes", json={"customer_id": "C002", "transaction_id": "T2001",
                                       "description": "I did not buy anything from ElectroWorld Lagos."})
    assert r.status_code == 201
    dispute = r.json()
    assert dispute["status"] == "needs_review"
    assert len(dispute["audit_logs"]) >= 7  # system start + 6 workflow steps

    # human approves
    r = client.post(f"/disputes/{dispute['id']}/review",
                    json={"reviewer": "ana", "decision": "refund", "note": "Confirmed with customer by phone."})
    assert r.status_code == 200
    reviewed = r.json()
    assert reviewed["status"] == "resolved"
    assert reviewed["audit_logs"][-1]["actor"] == "human:ana"

    # cannot review twice
    assert client.post(f"/disputes/{dispute['id']}/review",
                       json={"reviewer": "ana", "decision": "reject"}).status_code == 409

    # appears in search and filtered list
    assert any(d["id"] == dispute["id"] for d in client.get("/search", params={"q": "ElectroWorld"}).json())
    assert all(d["status"] == "resolved" for d in client.get("/disputes", params={"status": "resolved"}).json())


def test_api_key_is_enforced(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "secret")
    assert client.get("/disputes").status_code == 401
    assert client.get("/disputes", headers={"X-API-Key": "secret"}).status_code == 200