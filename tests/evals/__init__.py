"""Agent evals — behavioural tests for the chat agent.

Runs the real chat agent against real local data (data/datasets/, data/documents/)
with a real model call. Intended for engineers iterating on prompts. Not run in CI.

Wired into pre-commit so any change under backend/prompts/*.md triggers a run.
Cases live in tests/evals/customer/ — that's the customer carveout. The
runner, fixtures, and HTML report live here in template code.

Requires:
- Local data seeded (uv run python scripts/seed.py)
- OPENAI_API_KEY or Azure OpenAI creds in .env / .env.local

Run manually:
    uv run pytest tests/evals -v
    open tests/evals/report.html
"""
