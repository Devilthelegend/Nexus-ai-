"""Zero-dependency metrics with a Prometheus text-exposition renderer.

Provides small, thread-safe ``Counter``/``Gauge``/``Histogram`` collectors and a
``MetricsRegistry`` that renders them in the Prometheus 0.0.4 text format so the
app can serve ``/metrics`` without pulling in ``prometheus_client``. A real
client can later replace ``get_metrics`` behind the same surface.
"""

import threading
from functools import lru_cache

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
_DEFAULT_BUCKETS = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
)

_Labels = tuple[tuple[str, str], ...]


def _key(labels: dict[str, str]) -> _Labels:
    return tuple(sorted(labels.items()))


def _fmt(name: str, key: _Labels, value: float) -> str:
    if not key:
        return f"{name} {value}"
    inner = ",".join(f'{k}="{v}"' for k, v in key)
    return f"{name}{{{inner}}} {value}"


class _Scalar:
    """Base for labelled scalar collectors (counter/gauge)."""

    def __init__(self, name: str, help_text: str, typ: str) -> None:
        self.name = name
        self.help = help_text
        self.typ = typ
        self._values: dict[_Labels, float] = {}
        self._lock = threading.Lock()

    def _add(self, amount: float, labels: dict[str, str]) -> None:
        key = _key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def render(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} {self.typ}"]
        with self._lock:
            items = list(self._values.items()) or [((), 0.0)]
        lines.extend(_fmt(self.name, key, value) for key, value in items)
        return lines


class Counter(_Scalar):
    """Monotonically increasing value."""

    def __init__(self, name: str, help_text: str) -> None:
        super().__init__(name, help_text, "counter")

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        self._add(amount, labels)


class Gauge(_Scalar):
    """Value that can go up or down."""

    def __init__(self, name: str, help_text: str) -> None:
        super().__init__(name, help_text, "gauge")

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        self._add(amount, labels)

    def dec(self, amount: float = 1.0, **labels: str) -> None:
        self._add(-amount, labels)

    def set(self, value: float, **labels: str) -> None:
        with self._lock:
            self._values[_key(labels)] = value


class Histogram:
    """Cumulative-bucket histogram (unlabelled) with sum and count."""

    def __init__(
        self, name: str, help_text: str, buckets: tuple[float, ...] = _DEFAULT_BUCKETS
    ) -> None:
        self.name = name
        self.help = help_text
        self.buckets = tuple(sorted(buckets))
        self._counts = [0 for _ in self.buckets]
        self._sum = 0.0
        self._count = 0
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        with self._lock:
            self._sum += value
            self._count += 1
            for i, bound in enumerate(self.buckets):
                if value <= bound:
                    self._counts[i] += 1

    def render(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} histogram"]
        with self._lock:
            cumulative = 0
            for bound, count in zip(self.buckets, self._counts, strict=True):
                cumulative = count
                lines.append(f'{self.name}_bucket{{le="{bound}"}} {cumulative}')
            lines.append(f'{self.name}_bucket{{le="+Inf"}} {self._count}')
            lines.append(f"{self.name}_sum {self._sum}")
            lines.append(f"{self.name}_count {self._count}")
        return lines


class MetricsRegistry:
    """The application's collectors plus a text-format renderer."""

    def __init__(self) -> None:
        self.http_requests = Counter(
            "nexus_http_requests_total", "Total HTTP requests."
        )
        self.http_errors = Counter(
            "nexus_http_errors_total", "Total HTTP 5xx responses."
        )
        self.http_in_flight = Gauge(
            "nexus_http_requests_in_flight", "In-flight HTTP requests."
        )
        self.http_duration = Histogram(
            "nexus_http_request_duration_seconds", "HTTP request duration (s)."
        )
        self.llm_tokens = Counter(
            "nexus_llm_tokens_total", "Total LLM tokens processed."
        )
        self.llm_cost_usd = Counter(
            "nexus_llm_cost_usd_total", "Total estimated LLM cost (USD)."
        )
        self._collectors = (
            self.http_requests,
            self.http_errors,
            self.http_in_flight,
            self.http_duration,
            self.llm_tokens,
            self.llm_cost_usd,
        )

    def render(self) -> str:
        lines: list[str] = []
        for collector in self._collectors:
            lines.extend(collector.render())
        return "\n".join(lines) + "\n"


@lru_cache(maxsize=1)
def get_metrics() -> MetricsRegistry:
    """Return the process-wide metrics registry singleton."""
    return MetricsRegistry()
