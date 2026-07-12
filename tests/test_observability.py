"""Tests for Phase 5 observability and security hardening."""

from httpx import AsyncClient

from app.core.context import get_request_id, reset_request_id, set_request_id
from app.core.errors import error_body
from app.core.metrics import MetricsRegistry, get_metrics


def test_metrics_registry_renders_prometheus_text() -> None:
    reg = MetricsRegistry()
    reg.http_requests.inc(method="GET", status="200")
    reg.http_in_flight.inc()
    reg.http_duration.observe(0.02)
    reg.llm_tokens.inc(10.0)
    reg.llm_cost_usd.inc(0.5)

    text = reg.render()
    assert "# TYPE nexus_http_requests_total counter" in text
    assert 'nexus_http_requests_total{method="GET",status="200"} 1.0' in text
    assert "# TYPE nexus_http_request_duration_seconds histogram" in text
    assert "nexus_http_request_duration_seconds_count 1" in text
    assert "nexus_llm_tokens_total 10.0" in text


def test_get_metrics_is_singleton() -> None:
    assert get_metrics() is get_metrics()


def test_request_id_context_roundtrip() -> None:
    assert get_request_id() is None
    token = set_request_id("abc123")
    try:
        assert get_request_id() == "abc123"
    finally:
        reset_request_id(token)
    assert get_request_id() is None


def test_error_body_shape() -> None:
    body = error_body("not_found", "missing", details={"x": 1})
    assert set(body) == {"code", "message", "request_id", "details"}
    assert body["code"] == "not_found"
    assert body["message"] == "missing"
    assert body["details"] == {"x": 1}


async def test_metrics_endpoint_exposes_text(client: AsyncClient) -> None:
    await client.get("/healthz")
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "nexus_http_requests_total" in resp.text


async def test_request_id_is_echoed(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.headers.get("X-Request-ID")


async def test_request_id_is_propagated(client: AsyncClient) -> None:
    resp = await client.get(
        "/healthz", headers={"X-Request-ID": "trace-42"}
    )
    assert resp.headers.get("X-Request-ID") == "trace-42"


async def test_security_headers_present(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "no-referrer"
    assert "max-age" in resp.headers.get("Strict-Transport-Security", "")


async def test_error_envelope_on_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "not_found"
    assert body["request_id"] == resp.headers.get("X-Request-ID")


async def test_error_envelope_on_validation_error(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/login", json={"email": "x"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "validation_error"
    assert isinstance(body["details"], list)
