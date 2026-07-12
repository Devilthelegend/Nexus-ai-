"""Application entrypoint and FastAPI app factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Lifespan

from app.api import metrics
from app.api.v1 import health
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.observability import (
    MetricsMiddleware,
    RequestContextMiddleware,
    init_error_tracking,
    init_tracing,
)
from app.core.ratelimit import RateLimitMiddleware
from app.core.security_headers import SecurityHeadersMiddleware


def _build_lifespan(settings: Settings) -> Lifespan[FastAPI]:
    """Build a lifespan that optionally creates tables on startup.

    When ``db_auto_create`` is set (intended for local/offline runs such as
    SQLite), the schema is created from the ORM metadata so the app boots
    without a separate Alembic migration step. Production keeps this off and
    relies on migrations instead.
    """

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.db_auto_create:
            from app.db.session import engine
            from app.models import Base

            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        yield

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = settings or get_settings()
    configure_logging("DEBUG" if settings.debug else "INFO")
    init_error_tracking(settings)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=_build_lifespan(settings),
    )

    # Middleware runs bottom-up: rate limiting sits closest to the app while the
    # request-context (correlation id) wraps everything, so ids reach metrics,
    # security headers, throttled responses and error envelopes alike.
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestContextMiddleware)

    # Uniform error envelope with the correlation id on every failure.
    install_error_handlers(app)

    # Health probes and Prometheus metrics at the root for orchestrators.
    app.include_router(health.router)
    app.include_router(metrics.router)
    # Versioned business API.
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    # Minimal built-in web UI (single self-contained page) served from the same
    # origin as the API, so it shares auth and needs no CORS.
    web_dir = Path(__file__).resolve().parent / "web"
    if web_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=str(web_dir), html=True), name="ui")

        @app.get("/", include_in_schema=False)
        async def _root() -> RedirectResponse:
            return RedirectResponse(url="/ui/")

    # Optional distributed tracing (no-op unless enabled and installed).
    init_tracing(app, settings)

    return app


app = create_app()


def main() -> None:
    """Run the development server via ``python -m app.main``."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
