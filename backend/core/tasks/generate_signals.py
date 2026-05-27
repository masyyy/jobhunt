"""Background task: generate actionable signals via LLM."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent

from backend.core.agents.model_config import MODEL_MAIN, get_model
from backend.core.entities.task_output import TaskOutput
from backend.core.interfaces.task_output_repository import TaskOutputRepoFactory

logger = logging.getLogger(__name__)

TASK_NAME = "generate-signals"

SignalSeverity = Literal["high", "medium", "low"]

_INSTRUCTIONS = (
    "You generate actionable signals for an AI chatbot UI. "
    "Each signal represents something worth the user's attention. "
    "Return exactly 3 diverse signals. "
    "Each signal has: a brief title (5-8 words), a prompt the user would type "
    "(1-2 sentences, natural and conversational, no placeholders), "
    "a severity level (high, medium, or low), "
    "and a category that describes the signal's domain. "
    "Use context from the user message to pick relevant categories."
)


class SignalItem(BaseModel):
    title: str
    prompt: str
    severity: SignalSeverity
    category: str


class SignalList(BaseModel):
    signals: list[SignalItem]


async def generate_signals(
    *, repo_factory: TaskOutputRepoFactory, prompt: str | None = None, toolbox: str | None = None
) -> None:
    """Generate 3 LLM-powered signals and store them as task outputs."""
    agent: Agent[None, SignalList] = Agent(
        get_model(MODEL_MAIN),
        instructions=_INSTRUCTIONS,
        output_type=SignalList,
    )

    user_message = prompt or "Generate 3 diverse actionable signals."

    result = await agent.run(user_message)
    now = datetime.now(UTC)
    outputs = [
        TaskOutput(
            id=str(uuid.uuid4()),
            task_name=TASK_NAME,
            toolbox=toolbox,
            payload={**item.model_dump(), "state": "active"},
            created_at=now,
        )
        for item in result.output.signals
    ]

    async with repo_factory() as repo:
        await repo.replace_all(outputs, task_name=TASK_NAME, toolbox=toolbox)

    logger.info("Generated and saved %d signals", len(outputs))
