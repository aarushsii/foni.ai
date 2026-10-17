"""Talks to PRISM: (1) ask a guardrail before acting, (2) send a trace after.

If PRISM keys are missing, both functions do nothing, so the rest of the
code still runs while you are setting up.
"""
import requests
import config

HEADERS = {"Content-Type": "application/json", "X-PRISMtrace-Key": config.PRISM_API_KEY}


def check_guardrail(text: str, trace_id: str) -> dict:
    """Ask PRISM whether `text` breaks a block rule.

    Returns {"blocked": bool, "evaluated": bool, "rule_name": ..., ...}.
    PRISM only checks the LAST user message, so we send exactly one.
    """
    if not config.USE_PRISM:
        return {"blocked": False, "evaluated": False, "reason": "prism_not_configured"}
    try:
        r = requests.post(
            f"{config.PRISM_GUARDRAIL_HOST}/api/guardrails/evaluate",
            headers=HEADERS,
            json={
                "project_id": config.PRISM_PROJECT_ID,
                "trace_id": trace_id,          # same id as the trace -> block check works
                "agent_id": config.AGENT_ID,
                "messages": [{"role": "user", "content": text}],
            },
            timeout=8,
        )
        if r.status_code != 200:
            return {"blocked": False, "evaluated": False, "reason": f"http_{r.status_code}: {r.text[:200]}"}
        return r.json()
    except requests.RequestException as e:
        return {"blocked": False, "evaluated": False, "reason": f"error: {e}"}


def send_trace(*, trace_id, session_id, model, user_text, output, latency_ms, metadata) -> None:
    """Record one run in PRISM. After a block, `output` MUST be "" (empty),
    otherwise PRISM marks the block as 'Not honoured'."""
    if not config.USE_PRISM:
        return
    try:
        r = requests.post(
            f"{config.PRISM_HOST}/api/traces",
            headers=HEADERS,
            json={
                "project_id": config.PRISM_PROJECT_ID,
                "trace_id": trace_id,
                "session_id": session_id,
                "agent_id": config.AGENT_ID,
                "agent_name": config.AGENT_NAME,
                "model": model,
                "input_messages": [{"role": "user", "content": user_text}],
                "output_message": output,
                "latency_ms": int(latency_ms),
                "metadata": metadata,
            },
            timeout=8,
        )
        if r.status_code != 200:
            print(f"[prism] trace not saved: {r.status_code} {r.text[:200]}")
    except requests.RequestException as e:
        print(f"[prism] trace not saved: {e}")
