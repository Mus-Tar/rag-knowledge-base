from rag_api.app import create_app
from rag_api.config import Settings


def test_health_reports_service_version(settings: Settings, api_request) -> None:
    app = create_app(settings)

    response = api_request(app, "GET", "/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "rag-api",
        "version": "0.1.0",
    }


def test_production_disables_interactive_api_docs(settings: Settings, api_request) -> None:
    app = create_app(settings.model_copy(update={"app_env": "production"}))

    assert api_request(app, "GET", "/docs").status_code == 404
    assert api_request(app, "GET", "/redoc").status_code == 404
