from fastapi import FastAPI

from rag_api import __version__
from rag_api.api.errors import install_exception_handlers
from rag_api.api.routes.conversations import router as conversations_router
from rag_api.api.routes.documents import router as documents_router
from rag_api.api.routes.health import router as health_router
from rag_api.api.routes.metrics import router as metrics_router
from rag_api.application.conversations import ConversationService
from rag_api.application.documents import DocumentService
from rag_api.config import Settings, get_settings
from rag_api.infrastructure.database import Database
from rag_api.infrastructure.embeddings import create_embedding_provider
from rag_api.infrastructure.providers import create_provider
from rag_api.infrastructure.reranking import create_reranker
from rag_api.infrastructure.retrieval import ChromaRetriever
from rag_api.infrastructure.vector_store import ChromaVectorStore
from rag_api.metrics import IpRateLimiter, Metrics
from rag_api.observability import configure_logging, install_request_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    app = FastAPI(
        title=app_settings.app_name,
        version=__version__,
        docs_url="/docs" if app_settings.docs_enabled else None,
        redoc_url="/redoc" if app_settings.docs_enabled else None,
    )
    app_settings.resolved_data_dir.mkdir(parents=True, exist_ok=True)
    app_settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    database = Database(app_settings.database_url)
    database.initialize()
    embedding_provider = create_embedding_provider(app_settings)
    vector_store = ChromaVectorStore(
        app_settings.chroma_dir, embedding_provider, app_settings.index_version
    )
    retriever = ChromaRetriever(
        vector_store=vector_store,
        reranker=create_reranker(app_settings),
        limit=app_settings.retrieval_top_k,
        candidate_limit=app_settings.retrieval_candidate_k,
    )
    provider = create_provider(app_settings)
    app.state.settings = app_settings
    app.state.metrics = Metrics()
    app.state.rate_limiter = IpRateLimiter()
    app.state.document_service = DocumentService(app_settings, database, vector_store)
    app.state.conversation_service = ConversationService(
        app_settings, database, retriever, provider
    )
    install_exception_handlers(app)
    install_request_logging(app)
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(documents_router)
    app.include_router(conversations_router)
    return app
