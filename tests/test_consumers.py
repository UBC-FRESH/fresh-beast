"""Optional FEMIC/WS4 consumer compatibility checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _event() -> dict[str, object]:
    return {
        "schema_version": "femic.disturbance.v1",
        "event_id": "fresh-beast:33140:2018:neg-change",
        "event_type": "partial_mortality",
        "year": 2018,
        "severity_class": "unknown",
        "severity_value": None,
        "severity_basis": "BEAST negative NBR changepoint; no published severity mapping",
        "confidence": 0.9,
        "attribution": "BEAST/Rbeast",
        "attribution_method": "Rbeast harmonic changepoint probability, negative NBR trend",
        "block_ids": [33140],
        "area_ha": 1.44,
        "source_id": "hls-beast-nsr",
        "source_version": "fresh-beast 0.1.0a1",
        "retrieved_utc": "2026-10-27T00:00:00+00:00",
        "notes": "pilot",
    }


def test_femic_contract_accepts_event() -> None:
    """The emitted record is valid under FEMIC's disturbance contract."""
    disturbance = pytest.importorskip("femic.contracts.disturbance")
    disturbance.validate_disturbance_event(_event())


def test_ws4_consumer_loads_event(tmp_path: Path) -> None:
    """The same record is loadable by WS4's consumer reader."""
    disturbance = pytest.importorskip("ws4.disturbance")
    path = tmp_path / "events.json"
    path.write_text(json.dumps({"events": [_event()]}), encoding="utf-8")
    events = disturbance.load_disturbance_events(path)
    assert len(events) == 1
    assert events[0].event_id == "fresh-beast:33140:2018:neg-change"
    assert events[0].block_ids == (33140,)
