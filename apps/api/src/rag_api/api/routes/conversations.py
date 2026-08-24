import json
from collections.abc import Iterator
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from rag_api.api.dependencies import get_conversation_service
from rag_api.api.rate_limit import enforce_rate_limit
from rag_api.application.conversations import ConversationService
from rag_api.domain.exceptions import DocumentNotFound
from rag_api.domain.models import Citation, ConversationSummary, MessageSummary, RetrievalMetadata

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=255)


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class CreateMessageRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10000)


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class CitationResponse(BaseModel):
    document_id: str
    filename: str
    page: int
    chunk_id: str
    excerpt: str


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    citations: list[CitationResponse]
    created_at: datetime


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse]


class ConversationListResponse(BaseModel):
    conversations: list[ConversationResponse]


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    request: Request,
    payload: CreateConversationRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationResponse:
    enforce_rate_limit(request, "general")
    return _conversation_response(service.create(payload.title))


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    request: Request,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationListResponse:
    enforce_rate_limit(request, "general")
    return ConversationListResponse(
        conversations=[_conversation_response(item) for item in service.list()]
    )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def rename_conversation(
    conversation_id: str,
    request: Request,
    payload: RenameConversationRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationResponse:
    enforce_rate_limit(request, "general")
    try:
        return _conversation_response(service.rename(conversation_id, payload.title))
    except DocumentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: str,
    request: Request,
    service: ConversationService = Depends(get_conversation_service),
) -> None:
    enforce_rate_limit(request, "general")
    try:
        service.delete(conversation_id)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    conversation_id: str,
    request: Request,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationDetailResponse:
    enforce_rate_limit(request, "general")
    try:
        conversation, messages = service.get(conversation_id)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ConversationDetailResponse(
        **_conversation_response(conversation).model_dump(),
        messages=[_message_response(message) for message in messages],
    )


@router.post("/{conversation_id}/messages:stream")
def stream_message(
    conversation_id: str,
    request: Request,
    payload: CreateMessageRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> StreamingResponse:
    enforce_rate_limit(request, "chat")
    try:
        message_id, citations, retrieval, tokens = service.stream_answer(
            conversation_id, payload.question
        )
    except DocumentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return StreamingResponse(
        _events(message_id, citations, retrieval, tokens),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _events(
    message_id: str,
    citations: list[Citation],
    retrieval: RetrievalMetadata,
    tokens: Iterator[str],
) -> Iterator[str]:
    yield _event("message_start", {"message_id": message_id})
    yield _event("retrieval", retrieval.__dict__)
    for token in tokens:
        yield _event("token", {"text": token})
    yield _event("citations", {"items": [citation.__dict__ for citation in citations]})
    yield _event("message_end", {"message_id": message_id})


def _event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _conversation_response(summary: ConversationSummary) -> ConversationResponse:
    return ConversationResponse(**summary.__dict__)


def _message_response(message: MessageSummary) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        citations=[CitationResponse(**citation.__dict__) for citation in message.citations],
        created_at=message.created_at,
    )
