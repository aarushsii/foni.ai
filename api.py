"""The web API the Ninoo app calls.

Run locally:   uvicorn api:app --reload --port 8000
Then open:     http://localhost:8000/docs   (a page where you can test it)
"""
import json
from typing import Optional
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from pipeline import run

app = FastAPI(title="HoldUp API")

# Lets the Ninoo Builder app (a different website) call this API.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class Scenario(BaseModel):
    id: str = "live"
    transcript: str
    amount: float = 0
    method: str = "unknown"          # gift_card, wire, crypto, zelle, bank_transfer, check ...
    payee: str = "Unknown"
    known_contact: bool = False
    callback_verified: bool = False
    trusted_contact: str = "Sarah"   # the person Grandma chose to confirm big payments
    model: Optional[str] = None         # optional: try a different model
    version: Optional[str] = None       # optional: "v1" or "v2"


class Verification(BaseModel):
    trace_id: str
    approved: bool                   # True = Sarah says it's real, False = it's a scam


# Held payments waiting for the trusted contact (simulated, in memory).
HOLDS = {}


@app.get("/health")
def health():
    return {"ok": True, "llm": config.USE_LLM, "prism": config.USE_PRISM, "version": config.VERSION}


@app.post("/analyze")
def analyze(s: Scenario):
    data = s.model_dump()
    result = run(data, model=data.pop("model"), version=data.pop("version"))
    if result["decision"] == "HOLD":
        HOLDS[result["trace_id"]] = {"amount": data["amount"], "payee": data["payee"],
                                     "contact": data["trusted_contact"], "status": result["status"]}
    return result


@app.post("/verify")
def verify(v: Verification):
    """The trusted contact answers. Simulated: no real text message or payment."""
    hold = HOLDS.get(v.trace_id)
    if not hold:
        raise HTTPException(404, "No held payment with that trace_id")
    if hold["status"] != "HELD_PENDING_VERIFICATION":
        return {"trace_id": v.trace_id, **hold, "note": "Already decided"}
    hold["status"] = "RELEASED" if v.approved else "CANCELLED"
    msg = (f"{hold['contact']} confirmed it. The ${hold['amount']:,.0f} payment was sent (simulated)."
           if v.approved else
           f"{hold['contact']} said this is not real. The payment was cancelled and nothing was sent.")
    return {"trace_id": v.trace_id, **hold, "message": msg, "simulated": True}


@app.get("/holds")
def holds():
    """All held payments and their status, for the demo screen."""
    return HOLDS


DEMO_IDS = ["c01", "s01", "c26", "s04", "c17", "c44"]   # scams + legit calls for the demo buttons


@app.get("/scenarios")
def scenarios():
    """Ready-made simulated calls for the demo screen (scam and legit)."""
    out = []
    for path in ("scenarios.jsonl", "sample_scenarios.jsonl"):
        if os.path.exists(path):
            out += [json.loads(l) for l in open(path) if l.strip()]
    demo = [s for s in out if s.get("id") in DEMO_IDS]
    return {"demo": demo or out[:4], "all": out, "simulated": True}


@app.get("/scorecard")
def scorecard():
    """Returns Dev 2's results.json (catch rate, false-block rate per model and version)."""
    if os.path.exists("results.json"):
        with open("results.json") as f:
            return json.load(f)
    return {"status": "no results yet", "hint": "Dev 2: run_eval.py writes results.json"}
