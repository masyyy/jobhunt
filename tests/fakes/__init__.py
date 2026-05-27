"""Hand-written fakes for collaborators with no cheap real backing.

Only add a fake here when the real implementation can't be cheaply pointed at an
in-memory or temp store (LLM clients, external HTTP APIs). Everything else
should use the real implementation via fixtures in `tests/conftest.py`.
"""
