from __future__ import annotations

"""Shared constants for the Adaptive Hash Map metrics subsystem."""

SCHEMA_VERSION = "v1"

TICK_SCHEMA = "metrics.v1"
SUMMARY_SCHEMA = f"metrics.summary.{SCHEMA_VERSION}"
HEALTH_SCHEMA = f"metrics.health.{SCHEMA_VERSION}"
EVENTS_SCHEMA = f"metrics.events.{SCHEMA_VERSION}"
HISTORY_SCHEMA = f"metrics.history.{SCHEMA_VERSION}"
ERROR_SCHEMA = f"metrics.error.{SCHEMA_VERSION}"
LATENCY_HISTOGRAM_SCHEMA = "metrics.latency_histogram.v1"
PROBE_HISTOGRAM_SCHEMA = "metrics.probe_histogram.v1"
KEY_HEATMAP_SCHEMA = "metrics.key_heatmap.v1"

TOKEN_ENV_VAR = "_".join(("ADHASH", "TOKEN"))
AUTH_HEADER = "Authorization"
ALLOWED_METHODS = "GET, OPTIONS"
ALLOWED_HEADERS = f"{AUTH_HEADER}, Content-Type"
ALLOW_ORIGIN = "*"
CACHE_CONTROL = "no-store"
VARY_HEADER = "Accept-Encoding"
JSON_CONTENT_TYPE = "application/json"
PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4"

__all__ = [
    "SCHEMA_VERSION",
    "TICK_SCHEMA",
    "SUMMARY_SCHEMA",
    "HEALTH_SCHEMA",
    "EVENTS_SCHEMA",
    "HISTORY_SCHEMA",
    "ERROR_SCHEMA",
    "LATENCY_HISTOGRAM_SCHEMA",
    "PROBE_HISTOGRAM_SCHEMA",
    "KEY_HEATMAP_SCHEMA",
    "TOKEN_ENV_VAR",
    "AUTH_HEADER",
    "ALLOWED_METHODS",
    "ALLOWED_HEADERS",
    "ALLOW_ORIGIN",
    "CACHE_CONTROL",
    "VARY_HEADER",
    "JSON_CONTENT_TYPE",
    "PROMETHEUS_CONTENT_TYPE",
]
