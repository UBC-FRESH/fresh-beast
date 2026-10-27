"""Package-specific errors."""

from __future__ import annotations


class FreshBeastError(RuntimeError):
    """Raised when a fresh-beast operation cannot complete safely."""
