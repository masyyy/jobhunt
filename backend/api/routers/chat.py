import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic_ai import AgentRunResult, DeferredToolResults, ModelMessage
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.ui import SSE_CONTENT_TYPE
from pydantic_ai.ui.vercel_ai.request_types import (
    DynamicToolOutputAvailablePart,
    ToolOutputAvailablePart,
    UIMessage,
)
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from backend.api.auth import require_auth
from backend.api.dependencies import (
    get_agent_deps,
    get_compaction_service,
    get_conversation_repository,
    get_prompt_loader,
    get_repository_factory,
)
from backend.api.models.auth import AuthenticatedUser
from backend.api.models.chat import ConversationListItem, ConversationResponse
from backend.api.vercel_adapter import SDK_VERSION, FulcrumVercelAdapter
from backend.core.agents.chat_agent import create_agent
from backend.core.agents.deps import AgentDeps
from backend.core.agents.model_config import get_model_settings
from backend.core.interfaces.conversation_repository import ConversationRepositoryInterface, RepositoryFactory
from backend.core.interfaces.prompt_loader import PromptLoader
from backend.core.services.compaction import (
    CompactionService,
    load_all_messages_for_ui,
    load_messages_for_agent,
    save_messages_to_db,
)
from backend.customer import TOOLBOX_AGENT_CONFIG, PromptKey
from backend.customer.toolboxes import Toolbox

logger = logging.getLogger(__name__)

router = APIRouter()

# Cap on the number of unread streaming events held in memory per run.
# A connected client drains continuously and never approaches this; a
# disconnected client stops draining and we drop further events to bound
# memory. The agent run itself continues so on_complete still fires.
_AGENT_STREAM_QUEUE_MAXSIZE = 8192


def _build_deferred_tool_results(
    approval_results: DeferredToolResults | None,
    ui_messages: list[UIMessage],
) -> DeferredToolResults | None:
    """Combine approval responses and client-supplied tool outputs.

    ``approval_results`` is the adapter's extracted approval-response payload
    (from ``approval-responded`` parts). When the FE fulfils an
    ``ExternalToolset`` tool via ``addToolResult``, the assistant message
    carries an ``output-available`` part that we surface here as
    ``DeferredToolResults.calls`` so the agent can resume.

    Any ``output-available`` tool part on an FE-posted assistant message is
    treated as a deferred-call result — the client only re-sends an assistant
    message when ``sendAutomaticallyWhen`` triggers a resume turn after
    ``addToolResult``. Server-executed tool outputs were already persisted to
    the DB on the prior turn and are loaded via ``message_history``.
    """
    calls: dict[str, Any] = {}
    for msg in ui_messages:
        if msg.role != "assistant":
            continue
        for part in msg.parts:
            if isinstance(part, ToolOutputAvailablePart | DynamicToolOutputAvailablePart):
                calls[part.tool_call_id] = part.output

    if not calls:
        return approval_results
    if approval_results is None:
        return DeferredToolResults(calls=calls)
    return DeferredToolResults(approvals=approval_results.approvals, calls=calls)


def extract_new_user_message(request_messages: list[ModelMessage]) -> list[ModelMessage]:
    """Extract and validate the new user message from the request.

    The frontend sends only the latest message (not the full history).
    We validate it's a user request before persisting.
    """
    if not request_messages:
        return []
    last_msg = request_messages[-1]
    if isinstance(last_msg, ModelRequest) and any(isinstance(p, UserPromptPart) for p in last_msg.parts):
        return [last_msg]
    logger.warning(f"Last message in request is not a user prompt (kind={last_msg.kind}), skipping persistence")
    return []


@router.post("/conversation")
async def create_conversation(
    request: Request,
    user: AuthenticatedUser = Depends(require_auth),
    conversation_repository: ConversationRepositoryInterface = Depends(get_conversation_repository),
) -> ConversationResponse:
    """Create a new conversation"""
    toolbox_str = request.headers.get("x-toolbox")
    conversation = await conversation_repository.create_conversation(toolbox=toolbox_str, user_id=user.id)
    if not conversation.id:
        raise ValueError("Failed to create conversation")
    return ConversationResponse(conversation_id=conversation.id)


@router.get("/conversation/latest")
async def get_latest_conversation(
    user: AuthenticatedUser = Depends(require_auth),
    conversation_repository: ConversationRepositoryInterface = Depends(get_conversation_repository),
) -> ConversationResponse | None:
    """Get the latest conversation or None if no conversations exist"""
    conversation = await conversation_repository.get_latest_conversation(user_id=user.id)
    if not conversation:
        return None
    if not conversation.id:
        raise HTTPException(status_code=500, detail="Conversation missing ID")
    return ConversationResponse(conversation_id=conversation.id)


@router.get("/conversations")
async def list_conversations(
    request: Request,
    limit: int = 30,
    toolbox: str | None = None,
    user: AuthenticatedUser = Depends(require_auth),
    conversation_repository: ConversationRepositoryInterface = Depends(get_conversation_repository),
) -> list[ConversationListItem]:
    """List conversations with titles derived from the first user message."""
    # Accept toolbox from query param or header
    tb = toolbox or request.headers.get("x-toolbox")
    conversations = await conversation_repository.list_conversations(limit=limit, toolbox=tb, user_id=user.id)
    items = []
    for conv in conversations:
        title = "New conversation"
        if conv.messages and conv.messages[0].user_text:
            text = conv.messages[0].user_text
            title = text[:50] + "..." if len(text) > 50 else text
        items.append(
            ConversationListItem(
                conversation_id=conv.id or "",
                title=title,
                updated_at=conv.updated_at,
            )
        )
    return items


@router.delete("/conversation/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: AuthenticatedUser = Depends(require_auth),
    conversation_repository: ConversationRepositoryInterface = Depends(get_conversation_repository),
) -> dict[str, str]:
    """Delete a conversation and all its messages."""
    conv = await conversation_repository.get_conversation(conversation_id, user_id=user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    deleted = await conversation_repository.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted"}


@router.get("/conversation/history")
async def get_conversation_history(
    request: Request,
    toolbox: str | None = None,
    user: AuthenticatedUser = Depends(require_auth),
    conversation_repository: ConversationRepositoryInterface = Depends(get_conversation_repository),
) -> dict[str, Any]:
    """Get the latest conversation with messages in UI format."""
    tb = toolbox or request.headers.get("x-toolbox")
    conversation = await conversation_repository.get_latest_conversation(toolbox=tb, user_id=user.id)
    if not conversation or not conversation.id:
        return {"conversation_id": None, "messages": []}

    # Load ALL messages for UI display (not the compacted version for the agent)
    model_messages = await load_all_messages_for_ui(conversation.id, conversation_repository)

    # Use PydanticAI's built-in conversion to UI format
    ui_messages = FulcrumVercelAdapter.dump_messages(model_messages)

    # Convert to JSON-serializable format
    messages_json = [msg.model_dump(mode="json", by_alias=True) for msg in ui_messages]

    return {
        "conversation_id": conversation.id,
        "messages": messages_json,
    }


@router.get("/conversation/{conversation_id}/history")
async def get_conversation_history_by_id(
    conversation_id: str,
    user: AuthenticatedUser = Depends(require_auth),
    conversation_repository: ConversationRepositoryInterface = Depends(get_conversation_repository),
) -> dict[str, Any]:
    """Get a specific conversation's messages in UI format."""
    conv = await conversation_repository.get_conversation(conversation_id, user_id=user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    model_messages = await load_all_messages_for_ui(conversation_id, conversation_repository)
    ui_messages = FulcrumVercelAdapter.dump_messages(model_messages)
    messages_json = [msg.model_dump(mode="json", by_alias=True) for msg in ui_messages]

    return {
        "conversation_id": conversation_id,
        "messages": messages_json,
    }


def _create_on_complete(
    conversation_id: str,
    user_id: str,
    user_messages: list[ModelMessage],
    repo_factory: RepositoryFactory,
    compaction_service: CompactionService,
) -> Any:
    """Create an on_complete callback that saves messages to the database.

    Args:
        conversation_id: The conversation ID to save messages to.
        user_id: The owning user id, used to verify the conversation still
                 belongs to this user (defends against deletion + reuse races).
        user_messages: The user messages from the current request that need to be saved
                      (since new_messages() only returns messages created during the run).
        repo_factory: Factory for creating repository instances in the background callback.
        compaction_service: Injected compaction service for background summarization.
    """

    async def on_complete(result: AgentRunResult[Any]) -> AsyncIterator[Any]:
        """Save messages to database after streaming completes, then check for compaction."""
        try:
            # new_messages() excludes the user prompt when using the VercelAI adapter
            # (it comes via self.messages, not the prompt parameter), so we prepend it.
            new_messages = result.new_messages()
            all_new_messages = user_messages + new_messages

            # Save to database (background callback — needs its own session)
            async with repo_factory() as repo:
                # Check conversation still exists (may have been deleted during streaming)
                conv = await repo.get_conversation(conversation_id, user_id=user_id)
                if not conv:
                    logger.info(f"Conversation {conversation_id} was deleted during streaming, skipping persistence")
                    return

                await save_messages_to_db(conversation_id, all_new_messages, repo)

            logger.info(f"Saved {len(all_new_messages)} messages to conversation {conversation_id}")

            # Check and trigger compaction if needed (runs in background)
            if await compaction_service.check_needs_compaction(conversation_id):
                # Store task reference to prevent garbage collection
                _compaction_task = asyncio.create_task(compaction_service.run_compaction(conversation_id))
                _compaction_task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
                logger.info(f"Triggered compaction for {conversation_id}")

        except Exception as e:
            logger.error(f"Failed to save messages: {e}")

        # Yield nothing - we don't need to add extra events
        return
        yield  # Make this an async generator

    return on_complete


async def _run_agent_detached(
    adapter: FulcrumVercelAdapter,
    *,
    message_history: Sequence[ModelMessage],
    deps: AgentDeps,
    deferred_tool_results: DeferredToolResults | None = None,
    model_settings: Any,
    on_complete: Any,
    queue: asyncio.Queue[Any | None],
    conversation_id: str,
    user_id: str,
    user_messages: list[ModelMessage],
    repo_factory: RepositoryFactory,
) -> None:
    """Drive the agent stream to completion, push events to queue.

    Runs detached from the HTTP response. on_complete fires inside
    adapter.run_stream's iteration, so persistence is guaranteed
    regardless of client connectivity.

    If the model raises before on_complete fires (e.g. API timeout),
    persist at least the user message so the conversation is not
    silently empty.
    """
    on_complete_fired = False

    async def _tracked_on_complete(result: AgentRunResult[Any]) -> AsyncIterator[Any]:
        nonlocal on_complete_fired
        on_complete_fired = True
        async for ev in on_complete(result):
            yield ev

    dropped = 0
    try:
        async for event in adapter.run_stream(
            message_history=message_history,
            deferred_tool_results=deferred_tool_results,
            deps=deps,
            model_settings=model_settings,
            on_complete=_tracked_on_complete,
        ):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dropped += 1
    except Exception:
        logger.exception("Agent run failed for conversation %s", conversation_id)
        if not on_complete_fired and user_messages:
            try:
                async with repo_factory() as repo:
                    conv = await repo.get_conversation(conversation_id, user_id=user_id)
                    if conv:
                        await save_messages_to_db(conversation_id, user_messages, repo)
                        logger.info(
                            "Persisted user message after failed agent run for %s",
                            conversation_id,
                        )
            except Exception:
                logger.exception(
                    "Failed to persist user message after agent failure for %s",
                    conversation_id,
                )
    finally:
        if dropped:
            logger.warning(
                "Dropped %d stream event(s) for conversation %s: queue full (consumer disconnected or slow)",
                dropped,
                conversation_id,
            )
        # Sentinel must always be enqueued so a still-connected consumer
        # exits cleanly. Drop one buffered event if necessary.
        try:
            queue.put_nowait(None)
        except asyncio.QueueFull:
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
            queue.put_nowait(None)


async def _drain_queue(queue: asyncio.Queue[Any | None]) -> AsyncIterator[Any]:
    while True:
        chunk = await queue.get()
        if chunk is None:
            return
        yield chunk


async def _resolve_conversation_id(
    *,
    header_conversation_id: str | None,
    toolbox: Toolbox,
    user_id: str,
    repo: ConversationRepositoryInterface,
) -> str:
    """Resolve the conversation id for this turn: explicit header > latest > create new.

    Validates ownership and toolbox isolation when a header id is supplied.
    """
    if header_conversation_id:
        conv = await repo.get_conversation(header_conversation_id, user_id=user_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conv.toolbox is not None and conv.toolbox != toolbox.value:
            raise HTTPException(
                status_code=400,
                detail=f"Conversation belongs to toolbox '{conv.toolbox}', not '{toolbox.value}'",
            )
        return header_conversation_id

    conversation = await repo.get_latest_conversation(toolbox=toolbox.value, user_id=user_id)
    if conversation and conversation.id:
        return conversation.id
    new_conversation = await repo.create_conversation(toolbox=toolbox.value, user_id=user_id)
    if not new_conversation.id:
        raise ValueError("Failed to create conversation")
    return new_conversation.id


def _resolve_seed_message(
    *,
    raw_prompt_key: Any,
    toolbox: Toolbox,
    has_history: bool,
    prompt_loader: PromptLoader,
) -> ModelMessage | None:
    """Validate ``prompt_key`` against the toolbox config and load the seed prompt.

    Returns ``None`` when no kickoff seed applies (key absent, or conversation
    already has history). Raises ``HTTPException(422)`` for unknown / unaccepted
    keys on a true kickoff turn.
    """
    if raw_prompt_key is None or has_history:
        return None
    try:
        prompt_key = PromptKey(raw_prompt_key)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Unknown prompt_key: {raw_prompt_key}") from e
    if prompt_key not in TOOLBOX_AGENT_CONFIG[toolbox].accepted_prompt_keys:
        raise HTTPException(
            status_code=422,
            detail=f"prompt_key '{prompt_key.value}' is not accepted by toolbox '{toolbox.value}'",
        )
    seed_text = prompt_loader.load_seed(prompt_key.value)
    return ModelRequest(parts=[UserPromptPart(content=seed_text)])


def _make_done_callback(inflight: dict[str, asyncio.Task[None]], run_id: str) -> Any:
    def _on_done(task: asyncio.Task[None]) -> None:
        inflight.pop(run_id, None)
        if task.cancelled():
            logger.info("Agent run %s was cancelled", run_id)
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Agent run %s raised", run_id, exc_info=exc)

    return _on_done


@router.post("/chat")
async def chat(
    request: Request,
    user: AuthenticatedUser = Depends(require_auth),
    deps: AgentDeps = Depends(get_agent_deps),
    conversation_repository: ConversationRepositoryInterface = Depends(get_conversation_repository),
    repo_factory: RepositoryFactory = Depends(get_repository_factory),
    compaction_service: CompactionService = Depends(get_compaction_service),
    prompt_loader: PromptLoader = Depends(get_prompt_loader),
) -> Response:
    """Chat endpoint using Vercel AI SDK protocol with message persistence and compaction."""
    # Extract toolbox from header (required)
    toolbox_str = request.headers.get("x-toolbox")
    if not toolbox_str:
        raise HTTPException(status_code=422, detail="Missing required X-Toolbox header")
    try:
        toolbox = Toolbox(toolbox_str)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Unknown toolbox: {toolbox_str}") from e

    # Create toolbox-aware agent
    instructions = prompt_loader.load(toolbox.value)
    if not instructions:
        raise HTTPException(status_code=500, detail=f"No prompts loaded for toolbox: {toolbox.value}")
    chat_agent = create_agent(toolbox, instructions, tables=deps.db.list_tables())

    conversation_id = await _resolve_conversation_id(
        header_conversation_id=request.headers.get("x-conversation-id"),
        toolbox=toolbox,
        user_id=user.id,
        repo=conversation_repository,
    )

    # Load message history from database (with summary if available)
    message_history = await load_messages_for_agent(conversation_id, conversation_repository)

    logger.info(f"Loaded {len(message_history)} messages for conversation {conversation_id}")

    # Parse the request body. We extract our own `prompt_key` field before
    # handing the bytes to the adapter, which only sees the AI SDK shape.
    body = await request.body()
    try:
        body_json = json.loads(body) if body else {}
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from e

    seed_message = _resolve_seed_message(
        raw_prompt_key=body_json.get("prompt_key"),
        toolbox=toolbox,
        has_history=bool(message_history),
        prompt_loader=prompt_loader,
    )

    run_input = FulcrumVercelAdapter.build_run_input(body)

    if seed_message is not None:
        # Seed kickoff: ignore any FE-supplied messages, persist the seed as the first
        # user message. The adapter still needs run_input to drive the stream.
        new_user_messages: list[ModelMessage] = [seed_message]
        message_history = [seed_message]
    else:
        # Extract the new user message from the request (last message, validated as user prompt).
        # On HITL resume turns the last message is an assistant approval-response, not a
        # user prompt — extract_new_user_message returns [] in that case.
        all_request_messages = FulcrumVercelAdapter.load_messages(run_input.messages)
        new_user_messages = extract_new_user_message(all_request_messages)

    logger.info(f"Found {len(new_user_messages)} new user messages to persist")

    # Create on_complete callback with the user messages and session factory
    on_complete = _create_on_complete(conversation_id, user.id, new_user_messages, repo_factory, compaction_service)

    # Use the manual adapter pattern since we already parsed the body.
    # sdk_version=6 enables tool approval streaming (`approval-requested` /
    # `approval-responded` parts) for human-in-the-loop workflows.
    accept = request.headers.get("accept", SSE_CONTENT_TYPE)
    adapter = FulcrumVercelAdapter(
        agent=chat_agent,
        run_input=run_input,
        accept=accept,
        sdk_version=SDK_VERSION,
    )

    # On HITL resume turns the FE re-posts the conversation with the user's
    # decision on the last assistant message. Two flavours, both surfaced as
    # DeferredToolResults so the agent picks up where it left off:
    #   - Approvals (binary gate via `addToolApprovalResponse`) — the adapter
    #     extracts these from `approval-responded` parts into `.approvals`.
    #   - Client-supplied results (FE executes the tool via `addToolResult` for
    #     ExternalToolset tools like multi-choice prompts) — we walk the
    #     posted messages for `output-available` parts and load `.calls`.
    deferred_tool_results = _build_deferred_tool_results(adapter.deferred_tool_results, run_input.messages)

    # Spawn the agent run as a detached task so client disconnect doesn't
    # cancel persistence. The StreamingResponse consumes from a queue; when
    # the client disconnects, the consumer stops but the producer keeps
    # running until on_complete fires.
    queue: asyncio.Queue[Any | None] = asyncio.Queue(maxsize=_AGENT_STREAM_QUEUE_MAXSIZE)
    run_id = str(uuid4())

    inflight: dict[str, asyncio.Task[None]] = request.app.state.inflight_runs
    task = asyncio.create_task(
        _run_agent_detached(
            adapter,
            message_history=message_history,
            deferred_tool_results=deferred_tool_results,
            deps=deps,
            model_settings=get_model_settings(),
            on_complete=on_complete,
            queue=queue,
            conversation_id=conversation_id,
            user_id=user.id,
            user_messages=new_user_messages,
            repo_factory=repo_factory,
        ),
        name=f"agent-run-{run_id}",
    )
    inflight[run_id] = task
    task.add_done_callback(_make_done_callback(inflight, run_id))

    sse_event_stream = adapter.encode_stream(_drain_queue(queue))
    return StreamingResponse(sse_event_stream, media_type=accept)
