from fastapi import APIRouter, Request, Response

from rag_api.metrics import Metrics

router = APIRouter(tags=["system"])


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request) -> Response:
    registry: Metrics = request.app.state.metrics
    return Response(registry.render_prometheus(), media_type="text/plain; version=0.0.4")
