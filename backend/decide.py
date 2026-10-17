"""STEP 2 of 3: decide HOLD or ALLOW. Plain rules, no AI.

1. Legit path: a known contact whose request was confirmed by a callback goes through.
2. Otherwise add up the weighted signals into a risk score from 0 to 100.
3. Ask the PRISM guardrail. The enforce-mode Regex rule `risk=HIGH` blocks the
   payment, so PRISM itself enforces the hold.
"""
import config
import prism

WEIGHTS = {
    "urgency": 0.15,
    "secrecy": 0.20,
    "family_emergency": 0.15,
    "impersonation": 0.15,
    "unusual_payment": 0.25,
    "first_time_payee": 0.10,
}
RISKY_METHODS = {"gift_card", "wire", "crypto", "cash_courier", "bitcoin"}


def apply_payment_facts(signals: dict, s: dict) -> dict:
    """Facts we know for sure override the AI's guess."""
    def set_fact(name, score, text):
        sig = signals[name]
        sig["score"] = max(sig["score"], score)
        if not sig["evidence"]:
            sig["evidence"], sig["source"] = text, "payment_facts"

    if s.get("method") in RISKY_METHODS:
        set_fact("unusual_payment", 0.9, f"Payment method: {s['method'].replace('_', ' ')}")
    if not s.get("known_contact"):
        set_fact("first_time_payee", 1.0, f"{s.get('payee', 'Payee')} is not a saved contact")
    return signals


def risk_score(signals: dict) -> int:
    return round(100 * sum(WEIGHTS[k] * signals[k]["score"] for k in WEIGHTS))


def red_flag_combo(signals: dict, s: dict) -> str:
    """v2 only. Calm scams don't add up to a high score, but some COMBINATIONS are
    never normal. Returns the name of the combo, or "" if none."""
    if s.get("known_contact"):
        return ""
    if s.get("method") in RISKY_METHODS:
        return "risky_payment_to_new_payee"          # gift card / wire / crypto / courier to a stranger
    if signals["impersonation"]["score"] >= 0.5 and signals["unusual_payment"]["score"] >= 0.5:
        return "impersonation_plus_unusual_payment"  # "official" or "relative" + odd payment
    return ""


def decide(signals: dict, s: dict, trace_id: str, version: str = "v1") -> dict:
    # 1. Legit-emergency path: verified known contact -> minimal friction
    if s.get("known_contact") and s.get("callback_verified"):
        return {"decision": "ALLOW", "risk_score": risk_score(signals),
                "reason": "verified_known_contact", "guardrail": {"blocked": False, "evaluated": False}}

    score = risk_score(signals)
    combo = red_flag_combo(signals, s) if version == "v2" else ""
    if combo:
        score = max(score, config.HOLD_THRESHOLD)    # v2: a red-flag combo always reaches the hold line
    level = "HIGH" if score >= config.HOLD_THRESHOLD else "LOW"
    top = [k for k, v in sorted(signals.items(), key=lambda kv: -kv[1]["score"]) if v["score"] >= 0.5]

    # 2. PRISM enforces the hold. This exact text is what the Regex rule reads.
    request = (f"PAYMENT_REQUEST risk={level} score={score} amount={s.get('amount')} "
               f"method={s.get('method')} signals={','.join(top) or 'none'}")
    g = prism.check_guardrail(request, trace_id)

    # Hold if PRISM blocked it OR our own rule says HIGH. So nothing slips through
    # before Dev 2 has created the PRISM rule, or if PRISM is down.
    hold = bool(g.get("blocked")) or level == "HIGH"
    return {"decision": "HOLD" if hold else "ALLOW", "risk_score": score,
            "reason": (f"red_flag:{combo}" if combo else "risk_above_threshold") if hold else "risk_below_threshold",
            "top_signals": top, "guardrail": g, "guardrail_request": request}
