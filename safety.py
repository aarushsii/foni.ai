"""Local safety net: hides SSNs, card numbers and account numbers.

PRISM's PII guardrail is the main protection. This is a second layer so a
sensitive number never reaches the AI model or our own output, even if
PRISM is down.
"""
import re

SSN = re.compile(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b")
CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
ACCOUNT = re.compile(r"(?i)(account|acct|routing)(\s*(number|no\.?|#))?\s*[:\-]?\s*\d[\d -]{5,}")


def redact(text: str) -> str:
    text = CARD.sub("[CARD NUMBER HIDDEN]", text)
    text = SSN.sub("[SSN HIDDEN]", text)
    text = ACCOUNT.sub(lambda m: m.group(1) + " [NUMBER HIDDEN]", text)
    return text


def has_sensitive_number(text: str) -> bool:
    return redact(text) != text
