from typing import Any

from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.toolsets.external import ExternalToolset
from pydantic_ai.toolsets.function import FunctionToolset

from backend.core.agents.deps import AgentDeps
from backend.core.agents.model_config import MODEL_MAIN, get_model
from backend.core.interfaces.data_warehouse import TableInfo
from backend.core.services.compaction import prune_tool_outputs_processor
from backend.customer import TOOLBOX_AGENT_CONFIG, Toolbox


def build_schema_instructions(tables: list[TableInfo]) -> str:
    """Build a schema description string from available tables."""
    if not tables:
        return ""
    lines: list[str] = []
    for table in tables:
        col_defs = ", ".join(f"{col} ({dtype})" for col, dtype in table.columns.items())
        if table.description:
            lines.append(f"- **{table.name}** — *{table.description}*: {col_defs}")
        else:
            lines.append(f"- **{table.name}**: {col_defs}")
    return (
        "## Available Data Tables\n\n"
        "Use the `execute_sql` tool with DuckDB-compatible SELECT queries.\n"
        "Use ILIKE for case-insensitive text matching. "
        "Limit results to 200 rows unless the user asks for more.\n\n" + "\n".join(lines)
    )


def create_agent(toolbox: Toolbox, instructions: str, tables: list[TableInfo] | None = None) -> Agent[AgentDeps, Any]:
    """Create the chat agent for a toolbox using its ``AgentConfig``.

    Tools whose ``__name__`` appears in ``approval_required_tools`` are
    moved into a separate ``FunctionToolset(requires_approval=True)`` so
    the agent run pauses for human approval before executing them.

    ``external_tools`` are surfaced via an ``ExternalToolset`` so the model
    can call them; pydantic-ai pauses the run with ``DeferredToolRequests``
    and the chat router resumes when the FE supplies the result.

    When either pause mechanism is in play we widen ``output_type`` with
    ``DeferredToolRequests`` — pydantic-ai requires it on the union.
    """
    config = TOOLBOX_AGENT_CONFIG[toolbox]
    schema = build_schema_instructions(tables or [])
    full_instructions = f"{instructions}\n\n{schema}" if schema else instructions

    plain_tools = [t for t in config.tools if getattr(t, "__name__", None) not in config.approval_required_tools]
    approval_tools = [t for t in config.tools if getattr(t, "__name__", None) in config.approval_required_tools]

    toolsets: list[Any] = []
    if approval_tools:
        toolsets.append(FunctionToolset(approval_tools, requires_approval=True))
    if config.external_tools:
        toolsets.append(ExternalToolset(list(config.external_tools)))

    output_type: Any = config.output_type
    if approval_tools or config.external_tools:
        existing = output_type if isinstance(output_type, list) else [output_type]
        output_type = [*existing, DeferredToolRequests]

    return Agent(
        model=get_model(MODEL_MAIN),
        deps_type=AgentDeps,
        instructions=full_instructions,
        tools=plain_tools,
        toolsets=toolsets or None,
        output_type=output_type,
        history_processors=[prune_tool_outputs_processor],
    )
