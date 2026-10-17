# Phony — Dev 1 guide (agent + backend)

HoldUp pauses a payment when a phone call looks like a scam, explains why in plain
words, and proves it with PRISM.

## What each file does

| File | What it is | Do you edit it? |
|---|---|---|
| `config.py` | Reads your keys from `.env`, holds settings (model, v1/v2, threshold) | Rarely |
| `safety.py` | Hides SSNs, card and account numbers before anything reaches the AI | No |
| `prism.py` | Talks to PRISM: asks the guardrail, sends the trace | No |
| `signals.py` | **Step 1.** AI reads the transcript and scores 6 scam signals (0–1) | **Yes**: the v2 prompt |
| `decide.py` | **Step 2.** Plain rules: HOLD or ALLOW, plus the PRISM payment-hold guardrail | **Yes**: weights |
| `explain.py` | **Step 3.** The calm message for Grandma (a template, no AI) | Maybe the wording |
| `pipeline.py` | Runs steps 1→2→3 and sends the trace. You can run it from the terminal | No |
| `api.py` | The web API the Ninoo app calls (endpoints below) | No |
| `sample_scenarios.jsonl` | 6 quick test calls, for testing changes cheaply | No |
| `scenarios.jsonl` | 50 draft simulated calls (25 scams, 25 real), with tricky cases tagged `hard_` | PM reviews |
| `run_eval.py` | Runs all scenarios, writes `results.json` (catch rate, false-block rate) | No |
| `prism_check.py` | Checks the PRISM key and live connection | No |
| `render.yaml` | One-click deploy config for Render.com | No |

How one request flows:

```
transcript ──► PRISM PII guardrail ──blocked──► HOLD (no AI call)
                   │ ok
                   ▼
            signals.py (AI via Nicrron)
                   ▼
            decide.py ──► PRISM "risk=HIGH" guardrail ──► HOLD or ALLOW
                   ▼
            explain.py ──► message for Grandma
                   ▼
            PRISM trace (empty output if blocked, so the block check says "Honoured")
```

## API endpoints (for Dev 3)

| Endpoint | What it does |
|---|---|
| `POST /analyze` | Send a call + payment. Returns `decision` (HOLD/ALLOW), `status`, `evidence` (quotes from the call, each checked against the transcript), `explanation`, `risk_score` |
| `POST /verify` | The trusted contact answers: `{"trace_id": "...", "approved": true}` → RELEASED, `false` → CANCELLED |
| `GET /holds` | All held payments and their status |
| `GET /scorecard` | `results.json` from `run_eval.py`: per version and model |
| `GET /scenarios` | Simulated demo calls (`demo` = 6 good ones for buttons, `all` = everything) |
| `GET /health` | Shows whether the AI and PRISM are connected |

Demo flow: scam call → `/analyze` returns HOLD with quotes → Sarah taps "Not real" → `/verify` → CANCELLED.
Then a legit call (known contact, callback verified) → `/analyze` returns ALLOW straight away.

Every response carries `"simulated": true` and a disclaimer. Calls and payments are simulated.

Evidence is auditable: the AI must quote the call, and `verify_quotes()` in `signals.py`
checks each quote really appears in the transcript. Quotes that don't are never shown, and
are counted in the trace as `metadata.quotes_unverified` (Dev 2 can use this in the evaluator).

## Setup, start to finish

### 1. Put the files in your repo
```bash
cd ~/fintea
unzip ~/Downloads/holdup.zip
```

### 2. Install
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Add your keys
```bash
cp .env.example .env
```
Open `.env` and paste your Nicrron key. Get the PRISM project ID and API key from
whoever made the PRISM workspace (Settings → Project and Settings → API Keys).
Leave PRISM empty for now if you don't have it yet; the code still runs.

### 4. Test it in the terminal
```bash
python pipeline.py
python pipeline.py --file sample_scenarios.jsonl
```
The first line tells you if the AI and PRISM are ON. ✅ means the decision matched
the expected answer.

### 5. Test the API
```bash
uvicorn api:app --reload --port 8000
```
Open http://localhost:8000/docs, click `/analyze` → Try it out → Execute.

### 6. Push to GitHub
```bash
git add .
git commit -m "HoldUp pipeline and API"
git push
```
Check that `.env` is NOT on GitHub.

### 7. Make a public URL for Dev 3
Fastest: ngrok (`brew install ngrok`, sign up free at ngrok.com, then):
```bash
ngrok http 8000
```
Send Dev 3 the `https://....ngrok-free.app` link. Keep your laptop and uvicorn running.
More stable: deploy the repo on Render (render.com → New → Web Service,
start command `uvicorn api:app --host 0.0.0.0 --port $PORT`, add the `.env` values
as environment variables).

## What Dev 2 must set up in PRISM (tell them)

1. **Regex Pattern Match** rule, action **block**, name `payment-hold`, pattern `risk=HIGH`.
   This is the enforce-mode guardrail proof.
2. **PII / PHI Detection** rule, action **block**. If it blocks too many normal calls
   (names can count as PII), replace it with a Regex rule for SSNs and cards:
   `\b\d{3}-\d{2}-\d{4}\b|\b(?:\d[ -]?){13,16}\b`
3. Guardrails need the **Builder** plan (the MONEYTALKS#2 code).

Every trace carries `metadata.expected`, `metadata.correct` and `metadata.version`,
so Dev 2 can filter wrong answers and compare v1 vs v2.

## Making v2

1. Dev 2 shows you the Root Cause cluster (e.g. "fake bank calls slip through").
2. Edit `PROMPT_V2` in `signals.py`, or the `WEIGHTS` in `decide.py`.
3. Rerun the same scenarios:
```bash
python pipeline.py --file scenarios.jsonl --version v1
python pipeline.py --file scenarios.jsonl --version v2
```

## Trying other models
```bash
python pipeline.py --file scenarios.jsonl --model anthropic/claude-sonnet-5
python pipeline.py --file scenarios.jsonl --model openai/gpt-5.5
```
PRISM analyses 200 runs a day. Test with a few scenarios before running all of them.
