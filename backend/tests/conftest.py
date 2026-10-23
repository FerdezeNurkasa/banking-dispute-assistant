import os
import tempfile

# Use a throw-away SQLite database for tests (must be set before the app is imported)
_db = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["OPENSEARCH_URL"] = ""

import pytest
from langchain_core.messages import AIMessage

from app.agents import llm as llm_module
from app.agents.state import Decision, FraudAssessment, IntakeResult, PolicyCheck
from app.db import init_db
from app.seed import seed


class _Structured:
    def __init__(self, value, seen):
        self.value, self.seen = value, seen

    def invoke(self, messages):
        self.seen.extend(m.content for m in messages)  # remember what was "sent to the LLM"
        return self.value


class _ToolCaller:
    """Pretends to be an LLM with tools: first asks for tool calls, then writes a summary."""

    def __init__(self, plan, final_text, seen):
        self.plan, self.final_text, self.step, self.seen = plan, final_text, 0, seen

    def invoke(self, messages):
        self.seen.extend(str(m.content) for m in messages)
        if self.step < len(self.plan):
            calls = [{"name": n, "args": a, "id": f"call_{self.step}_{i}"} for i, (n, a) in enumerate(self.plan[self.step])]
            self.step += 1
            return AIMessage(content="", tool_calls=calls)
        return AIMessage(content=self.final_text)


class FakeLLM:
    def __init__(self, responses: dict, tool_plan: list, final_text: str = "Evidence collected."):
        self.responses, self.tool_plan, self.final_text = responses, tool_plan, final_text
        self.seen: list[str] = []  # every message text the agents sent to the "LLM"

    def with_structured_output(self, schema):
        return _Structured(self.responses[schema], self.seen)

    def bind_tools(self, _tools):
        return _ToolCaller(self.tool_plan, self.final_text, self.seen)


@pytest.fixture(scope="session", autouse=True)
def database():
    init_db()
    seed()


@pytest.fixture
def fake_llm(monkeypatch):
    """Call fake_llm(...) inside a test to choose what the 'LLM' answers."""
    def install(category="duplicate_charge", fraud=5, decision="refund", confidence=0.92, eligible=True, tool_plan=None):
        fake = FakeLLM(
            responses={
                IntakeResult: IntakeResult(category=category, summary="Customer disputes a charge.", key_facts=[]),
                FraudAssessment: FraudAssessment(fraud_score=fraud, signals=[], reasoning="test"),
                PolicyCheck: PolicyCheck(eligible=eligible, applied_rules=["P-01"], missing_information=[], reasoning="test"),
                Decision: Decision(decision=decision, confidence=confidence, rationale="test",
                                   customer_message="Dear [CUSTOMER], we are reviewing your case."),
            },
            tool_plan=tool_plan if tool_plan is not None else [],
        )
        monkeypatch.setattr(llm_module, "get_llm", lambda: fake)
        return fake
    return install