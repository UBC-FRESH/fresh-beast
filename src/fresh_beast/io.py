"""Small, dependency-light storage helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from affine import Affine
from rasterio.crs import CRS

from .errors import FreshBeastError


@dataclass(frozen=True)
class CompositeStack:
    """A regular 16-day NBR composite stack on one raster grid.

    Attributes
    ----------
    nbr : numpy.ndarray
        Float32 array with shape ``(time, rows, cols)``; NaN means no valid
        observation in that composite.
    counts : numpy.ndarray
        Number of valid HLS observations averaged into each composite.
    dates : numpy.ndarray
        Composite start dates as ``datetime64[D]``.
    crs : rasterio.crs.CRS
        Raster CRS.
    transform : affine.Affine
        Raster affine transform.
    bbox_wgs84 : tuple[float, float, float, float]
        Requested AOI in EPSG:4326.
    start : datetime.date
        First composite start date.
    end : datetime.date
        Exclusive end of the composite window.
    band_pairs : tuple[tuple[str, str], ...]
        ``(NIR, SWIR2)`` HLS band names used by each sensor family.
    mask_bits : int
        Fmask bits treated as invalid.
    """

    nbr: np.ndarray
    counts: np.ndarray
    dates: np.ndarray
    crs: CRS
    transform: Affine
    bbox_wgs84: tuple[float, float, float, float]
    start: date
    end: date
    band_pairs: tuple[tuple[str, str], ...]
    mask_bits: int

    @property
    def shape(self) -> tuple[int, int, int]:
        """Return the stack shape."""
        return (int(self.nbr.shape[0]), int(self.nbr.shape[1]), int(self.nbr.shape[2]))

    @property
    def pixel_area_ha(self) -> float:
        """Return pixel area in hectares."""
        determinant = abs(self.transform.a * self.transform.e - self.transform.b * self.transform.d)
        return determinant / 10_000.0

    @property
    def valid_fraction(self) -> float:
        """Return the fraction of finite composite cells."""
        if self.nbr.size == 0:
            return 0.0
        return float(np.isfinite(self.nbr).sum() / self.nbr.size)

    def summary(self) -> dict[str, object]:
        """Return a JSON-safe description of the stack."""
        return {
            "shape": list(self.shape),
            "pixel_area_ha": self.pixel_area_ha,
            "start": self.start.isoformat(),
            "end_exclusive": self.end.isoformat(),
            "crs": self.crs.to_string(),
            "transform": list(self.transform)[:6],
            "bbox_wgs84": list(self.bbox_wgs84),
            "band_pairs": [list(pair) for pair in self.band_pairs],
            "mask_bits": self.mask_bits,
            "valid_fraction": self.valid_fraction,
        }

    def save(self, path: Path) -> None:
        """Write the stack and its grid metadata to a compressed NPZ file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            nbr=self.nbr.astype(np.float32, copy=False),
            counts=self.counts.astype(np.int16, copy=False),
            dates=self.dates.astype("datetime64[D]"),
            crs_wkt=self.crs.to_wkt(),
            transform=np.asarray(list(self.transform)[:6], dtype="float64"),
            bbox_wgs84=np.asarray(self.bbox_wgs84, dtype="float64"),
            start=np.asarray(self.start.isoformat()),
            end=np.asarray(self.end.isoformat()),
            band_pairs=np.asarray(json.dumps([list(pair) for pair in self.band_pairs])),
            mask_bits=np.asarray(self.mask_bits, dtype="int16"),
        )

    @classmethod
    def load(cls, path: Path) -> CompositeStack:
        """Read a composite stack written by :meth:`save`."""
        if not path.exists():
            raise FreshBeastError(f"composite file does not exist: {path}")
        try:
            with np.load(path, allow_pickle=False) as data:
                return cls(
                    nbr=np.asarray(data["nbr"], dtype=np.float32),
                    counts=np.asarray(data["counts"], dtype=np.int16),
                    dates=np.asarray(data["dates"], dtype="datetime64[D]"),
                    crs=CRS.from_wkt(str(data["crs_wkt"])),
                    transform=Affine(*[float(value) for value in data["transform"]]),
                    bbox_wgs84=(
                        float(data["bbox_wgs84"][0]),
                        float(data["bbox_wgs84"][1]),
                        float(data["bbox_wgs84"][2]),
                        float(data["bbox_wgs84"][3]),
                    ),
                    start=date.fromisoformat(str(data["start"])),
                    end=date.fromisoformat(str(data["end"])),
                    band_pairs=tuple(
                        (str(pair[0]), str(pair[1]))
                        for pair in json.loads(str(data["band_pairs"]))
                    ),
                    mask_bits=int(data["mask_bits"]),
                )
        except (KeyError, ValueError, TypeError) as exc:
            raise FreshBeastError(f"invalid composite file {path}: {exc}") from exc


def write_json(path: Path, payload: Any) -> None:
    """Write JSON with stable indentation and a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
