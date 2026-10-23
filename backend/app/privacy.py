"""Masks personal data (PII) so it is never sent to the external LLM provider.

The original text stays in our own database (access-controlled); the LLM only sees placeholders
like [CARD_NUMBER]. This is data minimisation, a core GDPR principle.
"""
import re

# Order matters: IBAN before card numbers, because an IBAN also contains long digit groups.
PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,3})?\b")),
    ("CARD_NUMBER", re.compile(r"\b(?:\d[ -]?){12,18}\d\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("PHONE", re.compile(r"(?<![\w+])(?:(?:\+|00)\d{1,3}(?:[ /-]?\d{2,4}){2,4}|0\d{2}(?:[ /-]?\d{3}){2})\b")),
]


def mask_pii(text: str, names: list[str] | None = None) -> tuple[str, dict[str, int]]:
    """Returns the masked text and how many items of each type were masked."""
    counts: dict[str, int] = {}
    for label, pattern in PII_PATTERNS:
        text, n = pattern.subn(f"[{label}]", text)
        if n:
            counts[label] = n

    # Known names of the customer (full name first, then single parts like the first name)
    parts = []
    for name in names or []:
        parts.append(name)
        parts.extend(p for p in name.split() if len(p) > 2)
    for part in sorted(set(parts), key=len, reverse=True):
        text, n = re.subn(rf"\b{re.escape(part)}\b", "[CUSTOMER]", text, flags=re.IGNORECASE)
        if n:
            counts["NAME"] = counts.get("NAME", 0) + n
    return text, counts