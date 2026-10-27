"""Tests for BEAST-to-FEMIC event aggregation."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import geopandas as gpd
import numpy as np
from shapely.geometry import box

from fresh_beast.beast import BeastConfig, BeastOutput
from fresh_beast.events import actions_to_events, build_result
from fresh_beast.io import CompositeStack


def _fake_output(stack: CompositeStack, threshold: float = 0.5) -> BeastOutput:
    shape = stack.shape
    negative = np.zeros(shape, dtype=np.float32)
    year_2018 = stack.dates.astype("datetime64[Y]").astype(int) + 1970 == 2018
    negative[year_2018] = 0.9
    summaries: dict[str, dict[str, object]] = {
        f"p{row:04d}_{col:04d}": {
            "status": "ok",
            "max_neg_cp": "0.9",
            "max_neg_change": "-0.12",
        }
        for row in range(shape[1])
        for col in range(shape[2])
    }
    return BeastOutput(
        stack=stack,
        config=BeastConfig(threshold=threshold),
        time=np.arange(shape[0], dtype=float),
        cp_probability=negative.copy(),
        negative_probability=negative,
        trend=np.zeros(shape, dtype=np.float32),
        slope=np.zeros(shape, dtype=np.float32),
        summaries=summaries,
        rbeast_version="test",
        stdout="",
        stderr="",
    )


def test_events_aggregate_to_block(tmp_path: Path, synthetic_stack: CompositeStack) -> None:
    """One block/year event is emitted from pixel detections."""
    block_path = tmp_path / "blocks.geojson"
    blocks = gpd.GeoDataFrame(
        {"block_id": [33140]},
        geometry=[box(600000, 5800000 - 4 * 30, 600000 + 4 * 30, 5800000)],
        crs="EPSG:32610",
    ).to_crs("EPSG:4326")
    blocks.to_file(block_path, driver="GeoJSON")

    output = _fake_output(synthetic_stack)
    events = actions_to_events(output, block_path)
    assert len(events) == 1
    event = events[0]
    assert event["schema_version"] == "femic.disturbance.v1"
    assert event["event_type"] == "partial_mortality"
    assert event["year"] == 2018
    assert event["severity_class"] == "unknown"
    assert cast(list[int], event["block_ids"]) == [33140]
    assert cast(float, event["area_ha"]) == 16 * 0.09
    assert abs(float(str(event["confidence"])) - 0.9) < 1e-6
    assert "no published severity mapping" in str(event["severity_basis"])

    result = build_result(output, events)
    assert result["schema_version"] == "fresh.beast.v1"
    assert result["events"] == events
    assert cast(dict[str, object], result["beast"])["threshold"] == 0.5


def test_min_consecutive_years_suppresses_single_year(
    tmp_path: Path, synthetic_stack: CompositeStack
) -> None:
    """A one-year exceedance is suppressed when two years are required."""
    block_path = tmp_path / "blocks.geojson"
    blocks = gpd.GeoDataFrame(
        {"block_id": [33140]},
        geometry=[box(600000, 5800000 - 4 * 30, 600000 + 4 * 30, 5800000)],
        crs="EPSG:32610",
    ).to_crs("EPSG:4326")
    blocks.to_file(block_path, driver="GeoJSON")
    output = _fake_output(synthetic_stack, threshold=0.5)
    output = BeastOutput(
        stack=output.stack,
        config=BeastConfig(threshold=0.5, min_consecutive_years=2),
        time=output.time,
        cp_probability=output.cp_probability,
        negative_probability=output.negative_probability,
        trend=output.trend,
        slope=output.slope,
        summaries=output.summaries,
        rbeast_version=output.rbeast_version,
        stdout=output.stdout,
        stderr=output.stderr,
    )
    assert actions_to_events(output, block_path) == []
