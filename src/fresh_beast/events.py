"""Convert BEAST probabilities into FEMIC/WS4 disturbance events."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
from rasterio.features import rasterize
from shapely.geometry import box as shapely_box

from . import FRESH_BEAST_SCHEMA_VERSION, __version__
from .beast import BeastOutput, annual_negative_probability, beast_summary
from .errors import FreshBeastError
from .io import CompositeStack, write_json


@dataclass(frozen=True)
class PixelEvent:
    """One detected pixel-level NSR change."""

    row: int
    col: int
    year: int
    probability: float
    negative_change: float | None


def _groups(values: np.ndarray) -> list[list[int]]:
    """Group sorted integer years into consecutive runs."""
    if values.size == 0:
        return []
    groups: list[list[int]] = [[int(values[0])]]
    for value in values[1:]:
        current = int(value)
        if current == groups[-1][-1] + 1:
            groups[-1].append(current)
        else:
            groups.append([current])
    return groups


def pixel_events(output: BeastOutput) -> list[PixelEvent]:
    """Return one negative-change event per pixel and sustained episode."""
    years, annual, _ = annual_negative_probability(output)
    events: list[PixelEvent] = []
    for row in range(annual.shape[1]):
        for col in range(annual.shape[2]):
            series = annual[:, row, col]
            above = np.flatnonzero(np.isfinite(series) & (series >= output.config.threshold))
            if above.size == 0:
                continue
            selected_years = years[above]
            for group in _groups(selected_years):
                group_indices = np.asarray(
                    [int(np.flatnonzero(years == year)[0]) for year in group]
                )
                values = series[group_indices]
                best_local = int(np.nanargmax(values))
                best_index = int(group_indices[best_local])
                pixel_id = f"p{row:04d}_{col:04d}"
                summary = output.summaries.get(pixel_id, {})
                raw_change = summary.get("max_neg_change", "")
                try:
                    negative_change = (
                        float(str(raw_change)) if raw_change not in (None, "") else None
                    )
                except (TypeError, ValueError):
                    negative_change = None
                if len(group) < output.config.min_consecutive_years:
                    continue
                events.append(
                    PixelEvent(
                        row=row,
                        col=col,
                        year=int(years[best_index]),
                        probability=float(series[best_index]),
                        negative_change=negative_change,
                    )
                )
    return events


def _load_blocks(
    blocks_path: Path,
    bbox_wgs84: tuple[float, float, float, float],
    crs: object,
) -> gpd.GeoDataFrame:
    """Load the intersecting block polygons and reproject them to the grid."""
    if not blocks_path.exists():
        raise FreshBeastError(f"block file does not exist: {blocks_path}")
    blocks = gpd.read_file(blocks_path)
    if "block_id" not in blocks.columns:
        raise FreshBeastError("block file must contain a 'block_id' column")
    if blocks.crs is None:
        raise FreshBeastError("block file has no CRS")
    bbox = gpd.GeoDataFrame(
        {"geometry": [shapely_box(*bbox_wgs84)]}, crs="EPSG:4326"
    )
    blocks = blocks.to_crs("EPSG:4326")
    blocks = blocks[blocks.intersects(bbox.geometry.iloc[0])]
    if blocks.empty:
        raise FreshBeastError("no blocks intersect the composite AOI")
    blocks = blocks.to_crs(crs)
    blocks["block_id"] = blocks["block_id"].astype(int)
    blocks = blocks[blocks["block_id"] > 0]
    if blocks.empty:
        raise FreshBeastError("no positive block_id values intersect the composite AOI")
    return blocks


def _block_raster(
    blocks: gpd.GeoDataFrame,
    stack: CompositeStack,
) -> np.ndarray:
    """Rasterize block ids onto the composite grid."""
    shapes = (
        (geometry, int(block_id))
        for geometry, block_id in zip(blocks.geometry, blocks["block_id"], strict=False)
    )
    return np.asarray(
        rasterize(
            shapes,
            out_shape=(stack.nbr.shape[1], stack.nbr.shape[2]),
            transform=stack.transform,
            fill=0,
            dtype="int32",
            all_touched=False,
        )
    )


def _validate_with_femic(event: dict[str, object]) -> None:
    """Validate a full event with FEMIC when FEMIC is importable."""
    try:
        from femic.contracts.disturbance import validate_disturbance_event
    except ImportError:
        return
    validate_disturbance_event(event)


def actions_to_events(
    output: BeastOutput,
    blocks_path: Path,
    *,
    retrieved_utc: str | None = None,
) -> list[dict[str, object]]:
    """Aggregate pixel detections to ``femic.disturbance.v1`` block events."""
    pixels = pixel_events(output)
    blocks = _load_blocks(blocks_path, output.stack.bbox_wgs84, output.stack.crs)
    block_raster = _block_raster(blocks, output.stack)
    grouped: dict[tuple[int, int], list[PixelEvent]] = defaultdict(list)
    for pixel in pixels:
        block_id = int(block_raster[pixel.row, pixel.col])
        if block_id <= 0:
            continue
        grouped[(block_id, pixel.year)].append(pixel)
    if not grouped:
        return []

    timestamp = retrieved_utc or datetime.now(UTC).isoformat()
    area_per_pixel = output.stack.pixel_area_ha
    events: list[dict[str, object]] = []
    for (block_id, year), items in sorted(grouped.items()):
        probabilities = [item.probability for item in items]
        changes = [item.negative_change for item in items if item.negative_change is not None]
        notes = (
            "BEAST negative NBR changepoint; HLS 16-day composites; "
            f"threshold={output.config.threshold}; block={block_id}; "
            f"pixels={len(items)}; mean_negative_cp={np.mean(probabilities):.6f}; "
            f"max_negative_cp={max(probabilities):.6f}; "
            f"max_negative_change={max(changes):.6f}"
            if changes
            else "BEAST negative NBR changepoint; HLS 16-day composites; "
            f"threshold={output.config.threshold}; block={block_id}; "
            f"pixels={len(items)}; mean_negative_cp={np.mean(probabilities):.6f}; "
            f"max_negative_cp={max(probabilities):.6f}"
        )
        event: dict[str, object] = {
            "schema_version": "femic.disturbance.v1",
            "event_id": f"fresh-beast:{block_id}:{year}:neg-change",
            "event_type": "partial_mortality",
            "year": int(year),
            "severity_class": "unknown",
            "severity_value": None,
            "severity_basis": "BEAST negative NBR changepoint; no published severity mapping",
            "confidence": float(max(probabilities)),
            "attribution": "BEAST/Rbeast",
            "attribution_method": "Rbeast harmonic changepoint probability, negative NBR trend",
            "block_ids": [int(block_id)],
            "area_ha": float(len(items) * area_per_pixel),
            "source_id": "hls-beast-nsr",
            "source_version": f"fresh-beast {__version__}",
            "retrieved_utc": timestamp,
            "notes": notes,
        }
        _validate_with_femic(event)
        events.append(event)
    return events


def build_result(
    output: BeastOutput,
    events: list[dict[str, object]],
    *,
    aoi_source: str | None = None,
    block_source: str | None = None,
) -> dict[str, object]:
    """Build the ``fresh.beast.v1`` result document."""
    return {
        "schema_version": FRESH_BEAST_SCHEMA_VERSION,
        "generated_utc": datetime.now(UTC).isoformat(),
        "method": {
            "algorithm": "BEAST",
            "implementation": "Rbeast",
            "rbeast_version": output.rbeast_version,
            "season": "harmonic",
            "time_axis": "regular 16-day composites; annual period",
            "signal": "negative NBR changepoint probability",
            "threshold": output.config.threshold,
            "min_consecutive_years": output.config.min_consecutive_years,
            "min_valid_composites": output.config.min_valid,
            "event_type": "partial_mortality",
            "agent_attribution": None,
            "severity_mapping": None,
        },
        "aoi": {
            "bbox_wgs84": list(output.stack.bbox_wgs84),
            "block_source": block_source,
            "aoi_source": aoi_source,
        },
        "composites": output.stack.summary(),
        "beast": beast_summary(output),
        "events": events,
        "caveats": [
            "BEAST detects changepoints in NBR, not tree survival or a specific agent.",
            "No published BEAST-to-AOS severity mapping is applied; severity_class is unknown.",
            "HLS-only composites start in 2013 (L30) and 2015 (S30); "
            "Brown et al. used Landsat from 2000.",
            "A BEAST detection is not a validated AOS polygon match unless a separate "
            "validation join is supplied.",
        ],
    }


def write_outputs(
    output: BeastOutput,
    events: list[dict[str, object]],
    out_dir: Path,
    *,
    aoi_source: str | None = None,
    block_source: str | None = None,
) -> dict[str, Path]:
    """Write the event table and result document."""
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "events.json"
    result_path = out_dir / "result.json"
    paths: dict[str, Path] = {}
    if events:
        write_json(events_path, {"events": events})
        paths["events"] = events_path
    write_json(
        result_path,
        build_result(output, events, aoi_source=aoi_source, block_source=block_source),
    )
    paths["result"] = result_path
    return paths
