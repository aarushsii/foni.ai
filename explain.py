"""STEP 3 of 3: the calm, plain-language message for the user.

HOLD -> a TEMPLATE, never an AI call. After PRISM blocks, any AI call would make
        PRISM mark the block "Not honoured". Templates also can't leak numbers.
ALLOW -> a short friendly template (you can swap in an AI call later if you want).
"""
from safety import redact

PLAIN_NAMES = {
    "urgency": "the caller is rushing you",
    "secrecy": "the caller asked you to keep it a secret",
    "family_emergency": "the call is about a family member in trouble",
    "impersonation": "the caller may not be who they say they are",
    "unusual_payment": "they want gift cards, a wire, crypto or cash",
    "first_time_payee": "you have never paid this person before",
}


def explain(decision: dict, signals: dict, s: dict) -> dict:
    if decision["decision"] == "HOLD":
        reasons = [PLAIN_NAMES[k] for k in decision.get("top_signals", [])][:3]
        if str(decision.get("reason", "")).startswith("red_flag:") and not reasons:
            reasons = ["this payment method to a new payee is a common scam pattern"]
        if decision.get("reason") == "sensitive_info_shared":
            reasons = ["a Social Security, card or account number was shared on this call"]
        bullet = "\n".join(f"• {r}" for r in reasons) or "• this request matches a common scam pattern"
        # Cite the call: only quotes we confirmed are really in the transcript.
        quotes = list(dict.fromkeys(v["evidence"] for v in signals.values()
                                    if v["score"] >= 0.5 and v.get("quote_verified")))[:2]
        heard = ("\n\nWhat we heard on the call:\n" + "\n".join(f'“{q}”' for q in quotes)) if quotes else ""
        contact = s.get("trusted_contact") or "your trusted contact"
        message = (
            "We paused this payment to keep your money safe.\n\n"
            f"Here is why:\n{bullet}{heard}\n\n"
            f"Nothing has been sent. We've asked {contact} to confirm. "
            "You can also hang up and call your family member at the number you already have."
        )
        verification = f"Waiting for {contact} to confirm this payment."
    else:
        message = "This payment looks okay. You can go ahead."
        verification = None
    return {"explanation": redact(message), "verification": verification}
