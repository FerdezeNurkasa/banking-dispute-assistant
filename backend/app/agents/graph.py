"""
Workflow:

    privacy_guard -> intake -> investigator -+-> fraud_agent  -+-> decision -> router -> END
                                             +-> policy_agent -+
                                              (run in parallel)
"""
from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (decision_agent, fraud_agent, intake_agent, investigator_agent, policy_agent,
                              privacy_guard, router)
from app.agents.state import DisputeState


def build_graph():
    g = StateGraph(DisputeState)
    g.add_node("privacy_guard", privacy_guard)
    g.add_node("intake", intake_agent)
    g.add_node("investigator", investigator_agent)
    g.add_node("fraud_agent", fraud_agent)
    g.add_node("policy_agent", policy_agent)
    g.add_node("decision", decision_agent)
    g.add_node("router", router)

    g.add_edge(START, "privacy_guard")  # personal data is masked before any LLM sees it
    g.add_edge("privacy_guard", "intake")
    g.add_edge("intake", "investigator")
    g.add_edge("investigator", "fraud_agent")          # fan-out: both run in parallel
    g.add_edge("investigator", "policy_agent")
    g.add_edge(["fraud_agent", "policy_agent"], "decision")  # fan-in: wait for both
    g.add_edge("decision", "router")
    g.add_edge("router", END)
    return g.compile()


dispute_graph = build_graph()