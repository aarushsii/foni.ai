# Notes for coding agents working in this repo

Fony: a hold-and-verify layer for scam-call payments. Python, FastAPI.
Model calls go through the Nicrron API (OpenAI-compatible). See README.md.

## PRISM tracing (do not remove)

This project sends traces to PRISM. Env vars: `PRISMTRACE_API_KEY`,
`PRISMTRACE_PROJECT_ID`, `PRISMTRACE_HOST`.

Tracing is currently wired at: prism.py, pipeline.py, decide.py, config.py

**Standing rule.** Whenever you add or change an agent, chain, graph, tool,
retriever, or any entry point that calls a model, wire it to PRISM before you
finish. Unwired code is invisible in the dashboard. If you are unsure whether
something is covered, assume it is not and wire it.
