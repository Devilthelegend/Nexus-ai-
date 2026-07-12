"""Prometheus metrics exposition endpoint."""

from fastapi import APIRouter
from starlette.responses import Response

from app.core.metrics import CONTENT_TYPE, get_metrics

router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Expose collected metrics in the Prometheus text format."""
    return Response(content=get_metrics().render(), media_type=CONTENT_TYPE)
