from fastapi import Request

from rag_api.application.conversations import ConversationService
from rag_api.application.documents import DocumentService


def get_document_service(request: Request) -> DocumentService:
    return request.app.state.document_service


def get_conversation_service(request: Request) -> ConversationService:
    return request.app.state.conversation_service
