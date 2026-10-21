"""The agents. Each node receives the shared state and returns only the fields it updates."""
import json
import time
from datetime import datetime, timezone
from functools import wraps

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.agents import llm as llm_module
from app.agents.policies import retrieve_rules
from app.agents.state import Decision, DisputeState, FraudAssessment, IntakeResult, PolicyCheck
from app.agents.tools import INVESTIGATOR_TOOLS, TOOLS_BY_NAME, get_customer_history, get_transaction
from app.config import settings


def audited(agent_name: str):
    """Decorator: measures each agent and appends an audit entry with what it produced."""
    def wrapper(fn):
        @wraps(fn)
        def inner(state: DisputeState):
            start = time.perf_counter()
            update = fn(state)
            update["audit"] = [{
                "actor": agent_name,
                "action": fn.__doc__.strip().splitlines()[0] if fn.__doc__ else fn.__name__,
                "details": {k: v for k, v in update.items() if k != "audit"},
                "duration_ms": int((time.perf_counter() - start) * 1000),
                "at": datetime.now(timezone.utc).isoformat(),
            }]
            return update
        return inner
    return wrapper


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ 1. Intake agent
@audited("intake_agent")
def intake_agent(state: DisputeState) -> dict:
    """Classified the customer complaint"""
    transaction = get_transaction.invoke({"transaction_id": state["transaction_id"]})
    llm = llm_module.get_llm().with_structured_output(IntakeResult)
    result: IntakeResult = llm.invoke([
        SystemMessage("You are a bank dispute intake specialist. Classify the customer's complaint "
                      "about a card transaction. Be neutral and factual."),
        HumanMessage(f"Transaction: {json.dumps(transaction)}\n\nCustomer complaint: {state['description']}"),
    ])
    return {"transaction": transaction, "intake": result.model_dump()}


# ------------------------------------------------------------------ 2. Investigator agent (tool calling)
@audited("investigator_agent")
def investigator_agent(state: DisputeState) -> dict:
    """Investigated transaction history with tools"""
    llm = llm_module.get_llm().bind_tools(INVESTIGATOR_TOOLS)
    messages = [
        SystemMessage("You are a bank dispute investigator. Use the tools to collect evidence about the "
                      "disputed transaction: the transaction itself, the customer's history, possible "
                      "duplicate charges and previous charges at the same merchant. When you have enough "
                      "evidence, reply with a short factual evidence summary (no decision)."),
        HumanMessage(f"Dispute category: {state['intake']['category']}\n"
                     f"Customer ID: {state['customer_id']}\nTransaction ID: {state['transaction_id']}\n"
                     f"Complaint: {state['description']}"),
    ]
    tool_calls_log = []
    for _ in range(6):  # hard limit so the agent can never loop forever
        ai = llm.invoke(messages)
        messages.append(ai)
        if not ai.tool_calls:
            break
        for call in ai.tool_calls:
            tool = TOOLS_BY_NAME.get(call["name"])
            output = tool.invoke(call["args"]) if tool else {"error": f"Unknown tool {call['name']}"}
            tool_calls_log.append({"tool": call["name"], "args": call["args"],
                                   "result_preview": json.dumps(output)[:300]})
            messages.append(ToolMessage(content=json.dumps(output), tool_call_id=call["id"]))
    summary = ai.content or "Investigation stopped after reaching the tool-call limit."
    return {"evidence": {"summary": summary, "tool_calls": tool_calls_log}}


# ------------------------------------------------------------------ 3a. Fraud agent (rules + LLM)
def rule_based_fraud_signals(transaction: dict, history: dict) -> tuple[int, list[str]]:
    """Deterministic checks: explainable and testable without an LLM."""
    score, signals = 0, []
    others = [t for t in history.get("transactions", []) if t["id"] != transaction["id"]]
    home = history.get("customer", {}).get("home_country")

    if others:
        avg = sum(t["amount"] for t in others) / len(others)
        if transaction["amount"] > 3 * avg:
            score += 30
            signals.append(f"Amount {transaction['amount']:.2f} is {transaction['amount'] / avg:.1f}x the average ({avg:.2f})")
        if transaction["merchant"] not in {t["merchant"] for t in others}:
            score += 15
            signals.append(f"First purchase at merchant '{transaction['merchant']}'")
    if home and transaction["country"] != home:
        score += 25
        signals.append(f"Transaction country {transaction['country']} differs from home country {home}")
    if transaction["channel"] == "online":
        score += 10
        signals.append("Card-not-present (online) transaction")
    if 0 <= _parse_dt(transaction["created_at"]).hour < 6:
        score += 10
        signals.append("Made between 00:00 and 06:00")
    return min(score, 100), signals


@audited("fraud_agent")
def fraud_agent(state: DisputeState) -> dict:
    """Assessed fraud risk"""
    history = get_customer_history.invoke({"customer_id": state["customer_id"]})
    rule_score, rule_signals = rule_based_fraud_signals(state["transaction"], history)
    llm = llm_module.get_llm().with_structured_output(FraudAssessment)
    assessment: FraudAssessment = llm.invoke([
        SystemMessage("You are a fraud analyst at a bank. Score how likely it is that this transaction "
                      "is fraudulent (0-100). Consider the rule-based signals, the evidence and the complaint. "
                      "A duplicate charge or a cancelled subscription is a merchant error, not fraud."),
        HumanMessage(f"Complaint category: {state['intake']['category']}\n"
                     f"Complaint: {state['description']}\n"
                     f"Rule-based score: {rule_score}, signals: {rule_signals}\n"
                     f"Investigator evidence: {state['evidence']['summary']}"),
    ])
    final_score = round(0.5 * rule_score + 0.5 * assessment.fraud_score)
    return {"fraud": {"fraud_score": final_score, "rule_score": rule_score, "llm_score": assessment.fraud_score,
                      "signals": rule_signals + [s for s in assessment.signals if s not in rule_signals],
                      "reasoning": assessment.reasoning}}


# ------------------------------------------------------------------ 3b. Policy agent (retrieval + LLM)
@audited("policy_agent")
def policy_agent(state: DisputeState) -> dict:
    """Checked dispute against bank policy"""
    rules = retrieve_rules(state["intake"]["category"])
    days_since = (datetime.now(timezone.utc) - _parse_dt(state["transaction"]["created_at"])).days
    llm = llm_module.get_llm().with_structured_output(PolicyCheck)
    check: PolicyCheck = llm.invoke([
        SystemMessage("You are a bank compliance officer. Decide if the dispute is eligible under ONLY the "
                      "policy rules provided. Cite rule IDs. List any information still missing."),
        HumanMessage(f"Policy rules:\n" + "\n".join(f"{r['id']}: {r['text']}" for r in rules) +
                     f"\n\nDays since transaction: {days_since}\n"
                     f"Category: {state['intake']['category']}\nComplaint: {state['description']}\n"
                     f"Evidence: {state['evidence']['summary']}"),
    ])
    return {"policy": {**check.model_dump(), "days_since_transaction": days_since,
                       "rules_considered": [r["id"] for r in rules]}}


# ------------------------------------------------------------------ 4. Decision agent
@audited("decision_agent")
def decision_agent(state: DisputeState) -> dict:
    """Drafted the decision"""
    llm = llm_module.get_llm().with_structured_output(Decision)
    decision: Decision = llm.invoke([
        SystemMessage("You are a senior dispute officer. Based on the evidence, fraud assessment and policy "
                      "check, decide: refund, reject or escalate. Never reject when information is missing; "
                      "escalate instead. Write a clear rationale and a polite customer message."),
        HumanMessage(json.dumps({
            "complaint": state["description"], "transaction": state["transaction"],
            "intake": state["intake"], "evidence": state["evidence"]["summary"],
            "fraud": state["fraud"], "policy": state["policy"],
        }, default=str)),
    ])
    return {"decision": decision.model_dump()}


# ------------------------------------------------------------------ 5. Router (plain code, no LLM)
@audited("router")
def router(state: DisputeState) -> dict:
    """Routed the dispute"""
    reasons = []
    if state["decision"]["decision"] == "escalate":
        reasons.append("Decision agent escalated")
    if state["fraud"]["fraud_score"] >= settings.HUMAN_REVIEW_FRAUD_SCORE:
        reasons.append(f"Fraud score {state['fraud']['fraud_score']} >= {settings.HUMAN_REVIEW_FRAUD_SCORE}")
    if state["transaction"]["amount"] >= settings.HUMAN_REVIEW_AMOUNT:
        reasons.append(f"Amount >= {settings.HUMAN_REVIEW_AMOUNT:.0f} EUR")
    if state["decision"]["confidence"] < settings.MIN_AUTO_CONFIDENCE:
        reasons.append(f"Confidence {state['decision']['confidence']:.2f} below {settings.MIN_AUTO_CONFIDENCE}")
    return {"route": "needs_review" if reasons else "auto_resolved", "route_reasons": reasons}