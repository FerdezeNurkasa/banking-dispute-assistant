from app.agents.graph import dispute_graph
from app.agents.nodes import rule_based_fraud_signals
from app.agents.tools import find_similar_charges, get_customer_history, get_transaction


def _run(customer_id, transaction_id, description="The charge on my card looks wrong to me."):
    return dispute_graph.invoke({"dispute_id": 0, "customer_id": customer_id, "transaction_id": transaction_id,
                                 "description": description, "audit": []})


def test_tool_finds_duplicate_charge():
    result = find_similar_charges.invoke({"transaction_id": "T1002"})
    assert result["count"] == 1
    assert result["similar_charges"][0]["id"] == "T1001"


def test_rule_based_fraud_flags_suspicious_transaction():
    tx = get_transaction.invoke({"transaction_id": "T2001"})
    score, signals = rule_based_fraud_signals(tx, get_customer_history.invoke({"customer_id": "C002"}))
    assert score >= 80
    assert any("NG" in s for s in signals)


def test_rule_based_fraud_low_for_normal_purchase():
    tx = get_transaction.invoke({"transaction_id": "T1002"})
    score, _ = rule_based_fraud_signals(tx, get_customer_history.invoke({"customer_id": "C001"}))
    assert score < 30


def test_duplicate_charge_is_auto_resolved(fake_llm):
    fake_llm(category="duplicate_charge", fraud=5, decision="refund", confidence=0.92,
             tool_plan=[[("get_transaction", {"transaction_id": "T1002"}),
                         ("find_similar_charges", {"transaction_id": "T1002"})]])
    state = _run("C001", "T1002")

    assert state["route"] == "auto_resolved"
    assert state["decision"]["decision"] == "refund"
    # investigator really executed both tools
    assert [c["tool"] for c in state["evidence"]["tool_calls"]] == ["get_transaction", "find_similar_charges"]
    # every agent left an audit entry (fraud + policy ran in parallel, both recorded)
    actors = [a["actor"] for a in state["audit"]]
    for agent in ["intake_agent", "investigator_agent", "fraud_agent", "policy_agent", "decision_agent", "router"]:
        assert agent in actors


def test_high_amount_fraud_goes_to_human_review(fake_llm):
    fake_llm(category="unauthorized", fraud=90, decision="refund", confidence=0.9)
    state = _run("C002", "T2001", "I did not make this purchase, my card is with me.")

    assert state["route"] == "needs_review"
    assert state["fraud"]["fraud_score"] >= 70
    assert any("Amount" in r for r in state["route_reasons"])


def test_low_confidence_goes_to_human_review(fake_llm):
    fake_llm(category="subscription_cancelled", fraud=5, decision="refund", confidence=0.5)
    state = _run("C003", "T3001", "I cancelled StreamPlus last month but was charged again.")
    assert state["route"] == "needs_review"