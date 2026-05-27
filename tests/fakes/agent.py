"""Fake summarization agent. Stands in for `pydantic_ai.Agent[None, str]`.

Real LLM calls belong in `tests/evals/`, not the test suite. This fake satisfies
the duck-typed contract `CompactionService` uses (`await agent.run(prompt,
message_history=...)` returning an object with `.output`).
"""

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import ModelMessage


@dataclass
class FakeAgentCall:
    prompt: str
    message_history: list[ModelMessage]


@dataclass
class FakeAgentResult:
    output: str


@dataclass
class FakeSummarizationAgent:
    """Returns `output` (or raises `raises`) on every `run()` call.

    Captures every call in `calls` so tests can assert on what the service
    asked the LLM to do, without coupling to mock-style call assertions.
    """

    output: str = "Summary of the prior conversation."
    raises: Exception | None = None
    calls: list[FakeAgentCall] = field(default_factory=list)

    async def run(
        self,
        prompt: str,
        *,
        message_history: list[ModelMessage] | None = None,
        **_: Any,
    ) -> FakeAgentResult:
        self.calls.append(FakeAgentCall(prompt=prompt, message_history=list(message_history or [])))
        if self.raises is not None:
            raise self.raises
        return FakeAgentResult(output=self.output)
