"""Celery application factory (optional dependency).

Ingestion runs inline by default (``ingest_eager=True``); this module provides
the asynchronous execution path used when a Redis broker and Celery worker are
available. Celery is not a hard dependency, so the import is guarded and the
factory returns ``None`` when it is absent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings

if TYPE_CHECKING:
    from celery import Celery

try:
    from celery import Celery as _Celery
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    _Celery = None


def create_celery() -> Celery | None:
    """Build the Celery app, or ``None`` if Celery is not installed."""
    if _Celery is None:
        return None
    settings = get_settings()
    app = _Celery(
        "nexus",
        broker=settings.redis_url,
        backend=settings.redis_url,
    )
    app.conf.task_default_queue = "ingestion"
    app.conf.task_acks_late = True
    app.conf.task_reject_on_worker_lost = True
    app.autodiscover_tasks(["app.workers"])
    return app


celery_app = create_celery()
