"""Runs the whole thing: safety check -> signals -> decide -> explain -> PRISM trace.

Try it:
    python pipeline.py "Grandma it's me, I'm in jail, send gift cards, don't tell Mom"
    python pipeline.py --file sample_scenarios.jsonl
    python pipeline.py --file sample_scenarios.jsonl --version v2 --model openai/gpt-5.5
"""
import argparse
from typing import Optional
import json
import time
import uuid

import config
import prism
from safety import redact
from signals import analyze, verify_quotes, SIGNALS
from decide import decide, apply_payment_facts
from explain import explain


def run(s: dict, model: Optional[str] = None, version: Optional[str] = None) -> dict:
    model = model or config.DEFAULT_MODEL
    version = version or config.VERSION
    sid = s.get("id", "adhoc")
    run_id = uuid.uuid4().hex[:8]
    trace_id = f"{sid}-{version}-{run_id}"          # the DECISION trace (used by the guardrail)
    session_id = f"run-{sid}-{version}-{run_id}"    # one session per run -> PRISM builds a trajectory
    start = time.time()

    raw = s.get("transcript", "")
    safe_transcript = redact(raw)
    details = (f"amount=${s.get('amount')} method={s.get('method')} payee={s.get('payee')} "
               f"known_contact={s.get('known_contact', False)} callback_verified={s.get('callback_verified', False)}")
    trace_input = f"{details}\nTRANSCRIPT: {safe_transcript}"

    # 0. PII guardrail on the raw transcript. If an SSN/card was said, block BEFORE any AI call.
    pii = prism.check_guardrail(raw, trace_id)
    if pii.get("blocked"):
        signals = {k: {"score": 0.0, "evidence": "", "quote_verified": False} for k in SIGNALS}
        d = {"decision": "HOLD", "risk_score": 100, "reason": "sensitive_info_shared",
             "top_signals": [], "guardrail": pii}
        usage = {"model": model, "tokens_in": 0, "tokens_out": 0}
    else:
        # 1. signals (the only AI call) -> 2. decide (+ PRISM payment-hold guardrail)
        t0 = time.time()
        signals, usage = analyze(safe_transcript, details, model, version)
        signals = verify_quotes(signals, safe_transcript)   # before payment facts add non-quote evidence

        # Trace 1 of 2 (same session): the AI signal step. Its own trace_id, so the
        # block check on the decision trace below is not affected.
        prism.send_trace(
            trace_id=f"{trace_id}-signals", session_id=session_id, model=usage["model"],
            user_text=trace_input,
            output=json.dumps({k: {"score": v["score"], "quote": v["evidence"],
                                   "quote_verified": v["quote_verified"]} for k, v in signals.items()}),
            latency_ms=(time.time() - t0) * 1000,
            metadata={"step": "signals", "version": version, "scenario_id": sid,
                      "tokens_in": usage["tokens_in"], "tokens_out": usage["tokens_out"]},
        )
        signals = apply_payment_facts(signals, s)
        d = decide(signals, s, trace_id, version)

    # 3. explanation
    e = explain(d, signals, s)
    latency = (time.time() - start) * 1000
    blocked = bool(d.get("guardrail", {}).get("blocked"))

    # Trace 2 of 2: the decision. Blocked -> EMPTY output, so PRISM's block check says "Honoured".
    prism.send_trace(
        trace_id=trace_id, session_id=session_id, model=usage["model"],
        user_text=trace_input,
        output="" if blocked else f"DECISION: {d['decision']} (risk {d['risk_score']})\n{e['explanation']}",
        latency_ms=latency,
        metadata={
            "step": "decision", "version": version, "scenario_id": sid, "decision": d["decision"],
            "risk_score": d["risk_score"], "reason": d["reason"],
            "expected": s.get("expected"),  # from scenarios file, for Dev 2's evaluator
            "correct": (s.get("expected") == d["decision"]) if s.get("expected") else None,
            "blocked_by": d.get("guardrail", {}).get("rule_name"),
            "signals": {k: v["score"] for k, v in signals.items()},
            "quotes_verified": sum(1 for v in signals.values() if v.get("quote_verified")),
            # AI quotes NOT found in the transcript -> possible hallucination (good for the evaluator)
            "quotes_unverified": sum(1 for v in signals.values() if v["evidence"] and v["score"] >= 0.5
                                     and not v.get("quote_verified") and v.get("source") != "payment_facts"),
        },
    )

    evidence = [{"signal": k, "quote": v["evidence"]} for k, v in signals.items()
                if v["score"] >= 0.5 and v.get("quote_verified")]

    return {
        "id": sid, "trace_id": trace_id, "version": version, "model": usage["model"],
        "decision": d["decision"], "risk_score": d["risk_score"], "reason": d["reason"],
        "status": "HELD_PENDING_VERIFICATION" if d["decision"] == "HOLD" else "SENT",
        "evidence": evidence,
        "signals": signals, "explanation": e["explanation"], "verification": e["verification"],
        "simulated": True,
        "disclaimer": "Demo on simulated calls and payments. Not a substitute for fraud protection.",
        "guardrail": {"blocked": blocked, "evaluated": bool(d.get("guardrail", {}).get("evaluated")),
                      "rule_name": d.get("guardrail", {}).get("rule_name")},
        "expected": s.get("expected"), "latency_ms": round(latency),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("transcript", nargs="?", help="a call transcript to test")
    p.add_argument("--file", help="a .jsonl file of scenarios")
    p.add_argument("--model", default=None)
    p.add_argument("--version", default=None, choices=["v1", "v2"])
    a = p.parse_args()

    print(f"LLM: {'Nicrron ' + (a.model or config.DEFAULT_MODEL) if config.USE_LLM else 'OFF (no NICRRON_API_KEY, using keywords)'}"
          f" | PRISM: {'ON' if config.USE_PRISM else 'OFF (no PRISM keys)'}\n")

    if a.file:
        scenarios = [json.loads(line) for line in open(a.file) if line.strip()]
    else:
        scenarios = [{"id": "cli", "transcript": a.transcript or "Grandma it's me, I'm in jail. Send $2000 in gift cards right now and don't tell Mom.",
                      "amount": 2000, "method": "gift_card", "payee": "Unknown caller"}]

    for s in scenarios:
        r = run(s, a.model, a.version)
        mark = "" if not r["expected"] else ("  ✅" if r["expected"] == r["decision"] else f"  ❌ expected {r['expected']}")
        print(f"[{r['id']}] {r['decision']:5} risk={r['risk_score']:3} blocked={r['guardrail']['blocked']}{mark}")
    if not a.file:
        print("\n" + r["explanation"])


if __name__ == "__main__":
    main()
