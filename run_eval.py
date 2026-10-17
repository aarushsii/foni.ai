"""Runs every scenario, scores the results, and writes results.json (the scorecard).

    python run_eval.py --file scenarios.jsonl --version v1
    python run_eval.py --file scenarios.jsonl --version v2
    python run_eval.py --file scenarios.jsonl --models nicrron/auto,openai/gpt-5.5 --limit 10

Each run also sends traces to PRISM (2 per scenario). PRISM analyses 200 a day,
so use --limit while testing and run the full file only for v1 and v2.

Metrics (on SIMULATED calls only):
  catch rate       = scams we held        / all scams
  false-block rate = real requests we held / all real requests
"""
import argparse
import json
import os
from datetime import datetime, timezone

import config
from pipeline import run

RESULTS = "results.json"


def score(rows: list) -> dict:
    scams = [r for r in rows if r["expected"] == "HOLD"]
    legit = [r for r in rows if r["expected"] == "ALLOW"]
    caught = [r for r in scams if r["decision"] == "HOLD"]
    false_blocks = [r for r in legit if r["decision"] == "HOLD"]
    pct = lambda a, b: round(100 * len(a) / len(b), 1) if b else None
    return {
        "scenarios": len(rows),
        "scams": len(scams),
        "legit": len(legit),
        "caught": len(caught),
        "missed": len(scams) - len(caught),
        "false_blocks": len(false_blocks),
        "catch_rate": pct(caught, scams),
        "false_block_rate": pct(false_blocks, legit),
        "accuracy": pct([r for r in rows if r["decision"] == r["expected"]], rows),
        "prism_blocks": sum(1 for r in rows if r["guardrail"]["blocked"]),
        "unverified_quotes": sum(r["unverified_quotes"] for r in rows),
        "missed_scams": [r["id"] for r in scams if r["decision"] != "HOLD"],
        "false_blocked": [r["id"] for r in false_blocks],
        "errors": [r["id"] for r in rows if r.get("error")],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", default="scenarios.jsonl")
    p.add_argument("--version", default=None, choices=["v1", "v2"])
    p.add_argument("--models", default=None, help="comma-separated, e.g. nicrron/auto,openai/gpt-5.5")
    p.add_argument("--limit", type=int, default=None, help="only run the first N scenarios")
    a = p.parse_args()

    version = a.version or config.VERSION
    models = [m.strip() for m in a.models.split(",")] if a.models else [config.DEFAULT_MODEL]
    scenarios = [json.loads(l) for l in open(a.file) if l.strip()]
    scenarios = [s for s in scenarios if s.get("expected") in ("HOLD", "ALLOW")][: a.limit]

    n_traces = 2 * len(scenarios) * len(models)
    print(f"{len(scenarios)} scenarios x {len(models)} model(s), version {version}. "
          f"About {n_traces} PRISM traces (daily analysis limit: 200).\n")

    existing = json.load(open(RESULTS)) if os.path.exists(RESULTS) else {"runs": []}

    for model in models:
        rows = []
        for s in scenarios:
            try:
                r = run(s, model=model, version=version)
                rows.append({"id": r["id"], "expected": s["expected"], "decision": r["decision"],
                             "risk_score": r["risk_score"], "guardrail": r["guardrail"],
                             "unverified_quotes": sum(1 for v in r["signals"].values()
                                                      if v["evidence"] and v["score"] >= 0.5
                                                      and not v.get("quote_verified")
                                                      and v.get("source") != "payment_facts")})
            except Exception as e:  # keep going; one bad model reply shouldn't kill the run
                rows.append({"id": s.get("id"), "expected": s["expected"], "decision": "ERROR",
                             "risk_score": None, "guardrail": {"blocked": False},
                             "unverified_quotes": 0, "error": str(e)[:200]})
            last = rows[-1]
            ok = "✅" if last["decision"] == last["expected"] else "❌"
            print(f"  [{model}] {last['id']:6} {last['decision']:5} expected {last['expected']:5} {ok}")

        summary = {"version": version, "model": model,
                   "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "simulated": True, **score(rows)}
        # Keep one entry per (version, model): the newest replaces the old one.
        existing["runs"] = [x for x in existing["runs"]
                            if not (x["version"] == version and x["model"] == model)] + [summary]

        print(f"\n{model} {version}: catch rate {summary['catch_rate']}% "
              f"({summary['caught']}/{summary['scams']}), false-block rate {summary['false_block_rate']}% "
              f"({summary['false_blocks']}/{summary['legit']}), PRISM blocks {summary['prism_blocks']}")
        if summary["missed_scams"]:
            print(f"  missed scams: {', '.join(summary['missed_scams'])}")
        if summary["false_blocked"]:
            print(f"  wrongly blocked: {', '.join(summary['false_blocked'])}")
        print()

    existing["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    existing["note"] = "Measured on simulated calls and payments. Not a substitute for fraud protection."
    json.dump(existing, open(RESULTS, "w"), indent=2)
    print(f"Saved {RESULTS}. The API serves it at /scorecard.")


if __name__ == "__main__":
    main()
