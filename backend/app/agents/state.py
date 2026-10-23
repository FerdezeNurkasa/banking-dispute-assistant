import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field


class DisputeState(TypedDict, total=False):
    """Shared state that flows through the LangGraph workflow."""

    dispute_id: int
    customer_id: str
    transaction_id: str
    description: str

    privacy: dict
    transaction: dict
    intake: dict
    evidence: dict
    fraud: dict
    policy: dict
    decision: dict
    route: str  # "auto_resolved" | "needs_review"
    route_reasons: list[str]

    # operator.add = every node APPENDS its entries, so parallel agents never overwrite each other
    audit: Annotated[list[dict], operator.add]


# ---------- Structured outputs the LLM must return (validated by Pydantic) ----------

Category = Literal[
    "unauthorized", "duplicate_charge", "not_received",
    "wrong_amount", "subscription_cancelled", "other",
]


class IntakeResult(BaseModel):
    category: Category = Field(description="Dispute category that best matches the customer's complaint")
    summary: str = Field(description="One-sentence neutral summary of the complaint")
    key_facts: list[str] = Field(description="Facts stated by the customer, e.g. 'card still in my possession'")


class FraudAssessment(BaseModel):
    fraud_score: int = Field(ge=0, le=100, description="0 = clearly legitimate, 100 = clearly fraud")
    signals: list[str] = Field(description="Signals that influenced the score")
    reasoning: str


class PolicyCheck(BaseModel):
    eligible: bool = Field(description="Whether the dispute is eligible under bank policy")
    applied_rules: list[str] = Field(description="IDs of the policy rules applied, e.g. ['P-01', 'P-03']")
    missing_information: list[str] = Field(description="Information still needed from the customer")
    reasoning: str


class Decision(BaseModel):
    decision: Literal["refund", "reject", "escalate"]
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(description="Explanation for the bank employee, citing evidence and policy rules")
    customer_message: str = Field(description="Short, polite message to send to the customer")