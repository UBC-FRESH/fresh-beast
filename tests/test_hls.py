"""Tests for HLS index and composite helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from fresh_beast.hls import nbr_from_reflectance
from fresh_beast.io import CompositeStack


def test_nbr_masks_fmask_and_nodata() -> None:
    """NBR uses valid HLS reflectance and excludes masked pixels."""
    nir = np.asarray([[5000, 5000, -9999]], dtype=np.int16)
    swir = np.asarray([[2000, 2000, 2000]], dtype=np.int16)
    fmask = np.asarray([[0, 1, 0]], dtype=np.uint8)
    result = nbr_from_reflectance(nir, swir, fmask)
    assert np.isclose(result[0, 0], (0.5 - 0.2) / (0.5 + 0.2))
    assert np.isnan(result[0, 1])
    assert np.isnan(result[0, 2])


def test_nbr_fill_value_is_masked() -> None:
    """Fmask 255 is fill and cannot become a valid observation."""
    nir = np.asarray([[5000]], dtype=np.int16)
    swir = np.asarray([[2000]], dtype=np.int16)
    fmask = np.asarray([[255]], dtype=np.uint8)
    assert np.isnan(nbr_from_reflectance(nir, swir, fmask)[0, 0])


def test_stack_round_trip(tmp_path: Path, synthetic_stack: CompositeStack) -> None:
    """The composite file retains grid, dates, and provenance."""
    path = tmp_path / "stack.npz"
    synthetic_stack.save(path)
    loaded = CompositeStack.load(path)
    assert loaded.shape == synthetic_stack.shape
    assert loaded.crs == synthetic_stack.crs
    assert loaded.transform == synthetic_stack.transform
    assert np.array_equal(loaded.dates, synthetic_stack.dates)
    assert loaded.bbox_wgs84 == synthetic_stack.bbox_wgs84
    assert loaded.band_pairs == synthetic_stack.band_pairs
    assert np.isclose(loaded.pixel_area_ha, 0.09)
