"""STEP 1 of 3: read the call transcript and score the scam signals.

Uses an AI model through Nicrron. Each signal gets a score from 0 to 1
plus a short piece of evidence. If no Nicrron key is set, a simple
keyword checker is used instead so you can still test.
"""
import json
import re
from openai import OpenAI
import config

SIGNALS = ["urgency", "secrecy", "family_emergency", "impersonation", "unusual_payment", "first_time_payee"]

PROMPT_V1 = """You are a fraud analyst protecting an older adult from phone scams.
Read the call transcript and payment details. Score each signal from 0.0 (absent) to 1.0 (strong):

- urgency: pressure to act right now, threats, deadlines
- secrecy: asked to keep it secret ("don't tell Mom")
- family_emergency: a relative in trouble (jail, hospital, accident, stranded)
- impersonation: caller claims to be someone they may not be (grandchild, police, bank, IRS, lawyer)
- unusual_payment: gift cards, wire transfer, crypto, cash courier, or payment app to a stranger
- first_time_payee: money going to someone never paid before

For "evidence", copy the EXACT words from the transcript (a short quote, under 15 words).
If a signal is absent, use an empty string. Never invent words that are not in the transcript.

Reply with ONLY this JSON, no other text:
{"urgency": {"score": 0.0, "evidence": "short quote or reason"}, "secrecy": {...}, "family_emergency": {...}, "impersonation": {...}, "unusual_payment": {...}, "first_time_payee": {...}}"""

# v2: improve this after Dev 2 shows you the PRISM Root Cause cluster.
# Example fix below targets scams that have NO secrecy cue.
PROMPT_V2 = PROMPT_V1 + """

Important lessons from v1 mistakes. Many scams are CALM: no rushing, no secrecy, no emergency.
- Score impersonation high (0.8+) when ANY official (bank, police, IRS, Medicare, Social Security,
  tech support, a lawyer, a hospital) asks for money, a fee, or to move money to a new account,
  even if they sound polite and professional.
- Score impersonation high when a "relative" says they have a new or borrowed phone, or asks
  you to pay a friend or roommate instead of themselves.
- Score unusual_payment high (0.8+) when you must PAY to receive something (a prize, refund,
  benefit, or new card): that is an advance-fee scam. Also for paying a stranger via a payment app.
- Real banks, police and government never ask for gift cards, crypto, fees by phone, or to
  move money to a "safe" or "new" account."""


_CLIENT = None


def _client():
    """One shared client with a time limit: a slow AI call gives up after 25 s
    instead of hanging the whole server."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = OpenAI(base_url=config.NICRRON_BASE_URL, api_key=config.NICRRON_API_KEY,
                         timeout=25.0, max_retries=1)
    return _CLIENT


def _parse_json(text: str) -> dict:
    """Models sometimes wrap JSON in ``` fences or add words. Pull out the {...}."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON in model reply: {text[:200]}")
    return json.loads(match.group(0))


def _clean(raw: dict) -> dict:
    """Make sure every signal exists with a score between 0 and 1."""
    out = {}
    for name in SIGNALS:
        item = raw.get(name, {})
        if isinstance(item, (int, float)):
            item = {"score": item, "evidence": ""}
        try:
            score = float(item.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        out[name] = {"score": max(0.0, min(1.0, score)), "evidence": str(item.get("evidence", ""))[:200]}
    return out


def _norm(s: str) -> str:
    """Lowercase, unify curly quotes, drop punctuation, collapse spaces."""
    s = s.lower().replace("’", "'").replace("‘", "'")
    return " ".join(re.sub(r"[^a-z0-9' ]+", " ", s).split())


def verify_quotes(signals: dict, transcript: str) -> dict:
    """Auditability: mark each evidence quote True only if it really appears in the call.
    A quote the AI made up gets quote_verified=False and is never shown to the user."""
    words = _norm(transcript)
    for v in signals.values():
        q = _norm(v["evidence"]) if v["evidence"] else ""
        v["quote_verified"] = bool(q) and q in words
    return signals


def _keyword_fallback(text: str) -> dict:
    """Offline test mode only. Not used when a Nicrron key is set."""
    t = text.lower()

    def hit(words):
        for w in words:
            i = t.find(w)
            if i >= 0:
                # take the sentence around the keyword as the evidence quote
                start = max(t.rfind(".", 0, i), t.rfind("!", 0, i), t.rfind("?", 0, i)) + 1
                end = min([j for j in (t.find(".", i), t.find("!", i), t.find("?", i)) if j >= 0] or [len(t)])
                return {"score": 1.0, "evidence": text[start:end].strip()}
        return {"score": 0.0, "evidence": ""}

    return _clean({
        "urgency": hit(["right now", "immediately", "today", "hurry", "before it's too late", "urgent"]),
        "secrecy": hit(["don't tell", "do not tell", "keep this between", "secret"]),
        "family_emergency": hit(["jail", "hospital", "accident", "arrested", "bail", "stranded"]),
        "impersonation": hit(["grandma, it's me", "grandma it's me", "irs", "police", "officer", "bank", "lawyer", "attorney", "microsoft"]),
        "unusual_payment": hit(["gift card", "wire", "bitcoin", "crypto", "courier", "cash"]),
        "first_time_payee": {"score": 0.0},
    })


def analyze(transcript: str, details: str, model: str, version: str,
            allow_fallback: bool = False) -> tuple:
    """Returns (signals, usage). `transcript` must already be redacted.

    allow_fallback=True (used by the live API): if the AI call fails or times out,
    use the keyword checker instead of crashing, and mark the answer as degraded.
    The evaluator leaves it False so scorecard numbers are always real AI results."""
    if not config.USE_LLM:
        return _keyword_fallback(transcript), {"model": "offline-keywords", "tokens_in": 0, "tokens_out": 0}

    prompt = PROMPT_V2 if version == "v2" else PROMPT_V1
    try:
        reply = _client().chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"PAYMENT DETAILS:\n{details}\n\nCALL TRANSCRIPT:\n{transcript}"},
            ],
        )
        text = reply.choices[0].message.content or ""
        usage = {
            "model": reply.model or model,
            "tokens_in": getattr(reply.usage, "prompt_tokens", 0) or 0,
            "tokens_out": getattr(reply.usage, "completion_tokens", 0) or 0,
        }
        return _clean(_parse_json(text)), usage
    except Exception as e:
        if not allow_fallback:
            raise
        print(f"[signals] AI call failed, using keyword fallback: {str(e)[:150]}")
        return _keyword_fallback(transcript), {"model": "fallback-keywords", "tokens_in": 0,
                                               "tokens_out": 0, "degraded": True}
