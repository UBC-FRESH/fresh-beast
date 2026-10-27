"""BEAST/HLS NSR detection for the FRESH modelling ecosystem."""

from __future__ import annotations

__version__ = "0.1.0a1"

FRESH_BEAST_SCHEMA_VERSION = "fresh.beast.v1"
DEFAULT_THRESHOLD = 0.5
DEFAULT_COMPOSITE_DAYS = 16

__all__ = [
    "DEFAULT_COMPOSITE_DAYS",
    "DEFAULT_THRESHOLD",
    "FRESH_BEAST_SCHEMA_VERSION",
    "__version__",
]
