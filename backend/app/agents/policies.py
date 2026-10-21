"""Bank dispute policy. In a real bank this would come from a document store; the policy agent
retrieves only the rules relevant to the dispute category and passes them to the LLM."""

POLICY_RULES = [
    {"id": "P-01", "categories": ["*"],
     "text": "A dispute must be raised within 120 days of the transaction date."},
    {"id": "P-02", "categories": ["unauthorized"],
     "text": "For unauthorized transactions the card must be blocked and the customer must confirm "
             "they did not authorize or benefit from the payment."},
    {"id": "P-03", "categories": ["unauthorized"],
     "text": "Unauthorized transactions above 1,000 EUR or with strong fraud signals require review "
             "by the fraud team before any refund."},
    {"id": "P-04", "categories": ["duplicate_charge"],
     "text": "A duplicate charge is refundable when two or more charges with the same merchant and "
             "amount occur within 3 days and the customer received the goods/service only once."},
    {"id": "P-05", "categories": ["subscription_cancelled"],
     "text": "Charges for a subscription after the customer cancelled are refundable if the customer "
             "provides the cancellation date or confirmation; otherwise request it."},
    {"id": "P-06", "categories": ["not_received"],
     "text": "For goods not received, the customer must first contact the merchant and wait 15 days "
             "after the expected delivery date."},
    {"id": "P-07", "categories": ["wrong_amount"],
     "text": "If the charged amount differs from the agreed amount, only the difference is refundable."},
    {"id": "P-08", "categories": ["*"],
     "text": "When information is missing or evidence is contradictory, escalate to a human reviewer "
             "instead of rejecting."},
]


def retrieve_rules(category: str) -> list[dict]:
    return [r for r in POLICY_RULES if "*" in r["categories"] or category in r["categories"]]