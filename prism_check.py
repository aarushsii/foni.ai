"""Checks your PRISM setup in one command.

    python prism_check.py           -> step 1: proves your key works (handshake)
    python pipeline.py              -> sends a real (live) trace
    python prism_check.py           -> step 2 now shows LIVE CONNECTED
"""
import requests
import config

H = {"Content-Type": "application/json", "X-PRISMtrace-Key": config.PRISM_API_KEY}

if not config.USE_PRISM:
    raise SystemExit("Missing PRISMTRACE_API_KEY or PRISMTRACE_PROJECT_ID in .env")

# Step 1: prove the key works
r = requests.post(f"{config.PRISM_HOST}/api/setup-doctor/handshake", headers=H, timeout=15,
                  json={"project_id": config.PRISM_PROJECT_ID, "send_test_trace": True, "client": "claude_code"})
if r.status_code == 200:
    print("CREDENTIAL OK")
else:
    print(f"CREDENTIAL FAIL: {r.status_code} {r.text[:300]}")
    raise SystemExit(1)

# Step 2: has a live (non-test) trace arrived?
d = requests.get(f"{config.PRISM_HOST}/api/setup-doctor", headers=H, timeout=15,
                 params={"project_id": config.PRISM_PROJECT_ID}).json()
if d.get("live_connected"):
    print("LIVE CONNECTED: PRISM is receiving live traces from HoldUp.")
else:
    print(f"WAITING FOR LIVE: blocked at '{d.get('blocked_step')}'. "
          "Run `python pipeline.py` once, then run this check again.")
