"""Agent orchestration endpoints (workspace- and conversation-scoped)."""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import LLM, CurrentUser, DbSession, Embedder, Vectors
from app.models.message import Message
from app.schemas.agent import AgentRunRead, AgentRunRequest, AgentRunResponse
from app.schemas.conversation import MessageRead
from app.services import conversation_service
from app.services.agent import orchestrator
from app.services.exceptions import NotFoundError

router = APIRouter(
    prefix="/workspaces/{workspace_id}/conversations/{conversation_id}/agent",
    tags=["agents"],
)

_CONV_NOT_FOUND = "Conversation not found"
_RUN_NOT_FOUND = "Agent run not found"


async def _require_conversation(
    db: DbSession,
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
):
    try:
        return await conversation_service.get_for_user(
            db, workspace_id, conversation_id, current_user.id
        )
    except NotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, _CONV_NOT_FOUND
        ) from exc


@router.post(
    "/runs",
    response_model=AgentRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_run(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: AgentRunRequest,
    db: DbSession,
    current_user: CurrentUser,
    embedder: Embedder,
    store: Vectors,
    llm: LLM,
) -> AgentRunResponse:
    """Run the agent against the conversation's knowledge base."""
    conversation = await _require_conversation(
        db, workspace_id, conversation_id, current_user
    )
    run = await orchestrator.run_agent(
        db,
        conversation=conversation,
        objective=payload.objective,
        embedder=embedder,
        store=store,
        llm=llm,
    )
    answer = None
    if run.answer_message_id is not None:
        message = await db.get(Message, run.answer_message_id)
        if message is not None:
            answer = MessageRead.model_validate(message)
    return AgentRunResponse(run=AgentRunRead.model_validate(run), answer=answer)


@router.get("/runs", response_model=list[AgentRunRead])
async def list_runs(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> list[AgentRunRead]:
    """List the agent runs recorded for a conversation."""
    await _require_conversation(
        db, workspace_id, conversation_id, current_user
    )
    runs = await orchestrator.list_runs(db, conversation_id)
    return [AgentRunRead.model_validate(r) for r in runs]


@router.get("/runs/{run_id}", response_model=AgentRunRead)
async def get_run(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    run_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> AgentRunRead:
    """Retrieve a single agent run."""
    await _require_conversation(
        db, workspace_id, conversation_id, current_user
    )
    run = await orchestrator.get_run(db, conversation_id, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _RUN_NOT_FOUND)
    return AgentRunRead.model_validate(run)
