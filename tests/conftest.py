"""Shared test fixtures."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest
from affine import Affine
from rasterio.crs import CRS

from fresh_beast.io import CompositeStack


@pytest.fixture
def synthetic_stack() -> CompositeStack:
    """Return a 4x4, 2013-2018 stack with a 2018 NBR drop."""
    start = date(2013, 1, 1)
    end = date(2019, 1, 1)
    n_steps = (end - start).days // 16
    dates = np.asarray(
        [np.datetime64(start + timedelta(days=16 * index), "D") for index in range(n_steps)]
    )
    time = np.arange(n_steps)
    base = 0.55 + 0.08 * np.sin(2 * np.pi * time / 23)
    nbr = np.empty((n_steps, 4, 4), dtype=np.float32)
    for row in range(4):
        for col in range(4):
            series = base + np.random.default_rng(row * 4 + col).normal(0, 0.015, n_steps)
            series[time >= 115] -= 0.12
            nbr[:, row, col] = series
    return CompositeStack(
        nbr=nbr,
        counts=np.ones_like(nbr, dtype=np.int16),
        dates=dates,
        crs=CRS.from_epsg(32610),
        transform=Affine(30, 0, 600000, 0, -30, 5800000),
        bbox_wgs84=(-121.533, 52.339, -121.529, 52.342),
        start=start,
        end=end,
        band_pairs=(("B05", "B07"), ("B8A", "B12")),
        mask_bits=31,
    )
