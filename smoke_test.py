"""Checks the live backend end to end, the way Dev 3's app uses it.

    python smoke_test.py                                   # tests http://localhost:8000
    python smoke_test.py https://xxxx.trycloudflare.com    # tests the public link

Runs 1 scam + 1 real call (4 PRISM traces). Prints PASS/FAIL for each step.
"""
import sys
import time
import requests

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
ok_all = True


def check(name, fn):
    global ok_all
    t = time.time()
    try:
        detail = fn()
        print(f"PASS  {name:34} {time.time() - t:5.1f}s  {detail}")
    except Exception as e:
        ok_all = False
        print(f"FAIL  {name:34} {time.time() - t:5.1f}s  {str(e)[:160]}")


def get(path):
    r = requests.get(BASE + path, timeout=15)
    r.raise_for_status()
    return r.json()


def post(path, body, timeout=60):
    r = requests.post(BASE + path, json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


state = {}

print(f"Testing {BASE}\n")


def health():
    h = get("/health")
    assert h["ok"], h
    warn = []
    if not h["llm"]: warn.append("AI OFF (no Nicrron key?)")
    if not h["prism"]: warn.append("PRISM OFF (no PRISM keys?)")
    if h["version"] != "v2": warn.append(f"version is {h['version']}, demo should be v2")
    return f"version={h['version']} llm={h['llm']} prism={h['prism']}" + (f"  ⚠️ {'; '.join(warn)}" if warn else "")


def scenarios():
    d = get("/scenarios")
    assert d["demo"], "no demo scenarios"
    return f"{len(d['demo'])} demo calls, {len(d['all'])} total"


def scam():
    r = post("/analyze", {"transcript": "Grandma, it's me. I'm in jail and need bail right now. "
                          "Please buy gift cards and don't tell Mom.", "amount": 2000,
                          "method": "gift_card", "payee": "Unknown caller"})
    assert r["decision"] == "HOLD", f"expected HOLD, got {r['decision']}"
    state["trace_id"] = r["trace_id"]
    notes = []
    if not r["guardrail"]["blocked"]: notes.append("⚠️ PRISM did not block (rule missing or scoped to another agent?)")
    if r.get("degraded"): notes.append("⚠️ AI was down, backup answered")
    if not r["evidence"]: notes.append("⚠️ no evidence quotes")
    return f"HOLD risk={r['risk_score']} quotes={len(r['evidence'])} prism_blocked={r['guardrail']['blocked']} " + " ".join(notes)


def verify():
    v = post("/verify", {"trace_id": state["trace_id"], "approved": False})
    assert v["status"] == "CANCELLED", v
    return v["message"]


def legit():
    r = post("/analyze", {"transcript": "Hi Mom, it's Sarah. The tow truck is $350. I'm calling from my "
                          "usual number, like we agreed.", "amount": 350, "method": "zelle",
                          "payee": "Sarah Lee", "known_contact": True, "callback_verified": True})
    assert r["decision"] == "ALLOW", f"expected ALLOW, got {r['decision']}"
    return f"ALLOW risk={r['risk_score']}"


def scorecard():
    d = get("/scorecard")
    runs = d.get("runs", [])
    assert runs, "no results yet (run run_eval.py)"
    return "  ".join(f"{x['version']}: catch {x['catch_rate']}% false-block {x['false_block_rate']}%" for x in runs)


check("1. /health (server up)", health)
check("2. /scenarios (demo buttons)", scenarios)
check("3. /analyze scam -> HOLD", scam)
check("4. /verify Sarah says 'not real'", verify)
check("5. /analyze real call -> ALLOW", legit)
check("6. /scorecard (v1 vs v2)", scorecard)

print("\n✅ ALL GOOD" if ok_all else "\n❌ Something failed. Paste this output to get help.")
