"""HLS search, NBR calculation, and 16-day compositing."""

from __future__ import annotations

import math
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import earthaccess
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

from .errors import FreshBeastError
from .io import CompositeStack

DEFAULT_MASK_BITS = 0b00011111
SENSOR_BANDS: dict[str, tuple[str, str]] = {
    "HLSL30": ("B05", "B07"),
    "HLSS30": ("B8A", "B12"),
}
HLS_COLLECTIONS = tuple(SENSOR_BANDS)


@dataclass(frozen=True)
class HlsGranule:
    """Provenance for one opened HLS granule."""

    native_id: str
    short_name: str
    beginning_utc: str
    size_mb: float | None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe record."""
        return {
            "native_id": self.native_id,
            "short_name": self.short_name,
            "beginning_utc": self.beginning_utc,
            "size_mb": self.size_mb,
        }


def login_earthdata(strategy: str = "netrc") -> None:
    """Authenticate to NASA Earthdata.

    Parameters
    ----------
    strategy : str, optional
        ``earthaccess`` login strategy. The default ``netrc`` is the
        non-interactive option recommended by the package.

    Raises
    ------
    FreshBeastError
        If authentication fails.
    """
    try:
        authenticated = earthaccess.login(strategy=strategy)
    except Exception as exc:  # earthaccess raises several provider-specific errors.
        raise FreshBeastError(
            "Earthdata login failed. Put credentials in ~/.netrc (mode 600) "
            "or run `earthaccess.login()` interactively, then retry."
        ) from exc
    if not authenticated:
        raise FreshBeastError(
            "Earthdata login did not return an authenticated session. "
            "Check the LP DAAC/HLS application authorization."
        )


def _granule_date(granule: Any) -> datetime:
    """Return the granule acquisition timestamp in UTC."""
    umm = granule["umm"]
    extent = umm.get("TemporalExtent") or umm.get("TemporalCoverage")
    if not extent:
        raise FreshBeastError("HLS granule has no temporal extent")
    value = extent["RangeDateTime"]["BeginningDateTime"]
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _granule_record(granule: Any, short_name: str) -> HlsGranule:
    """Build provenance for a granule."""
    native_id = str(granule["meta"]["native-id"])
    size = granule.get("size")
    return HlsGranule(
        native_id=native_id,
        short_name=short_name,
        beginning_utc=_granule_date(granule).isoformat(),
        size_mb=float(size) if size is not None else None,
    )


def search_hls(
    bbox_wgs84: tuple[float, float, float, float],
    start: date,
    end_exclusive: date,
    short_name: str,
) -> list[Any]:
    """Search one HLS collection over an AOI and date range."""
    if end_exclusive <= start:
        raise FreshBeastError("end must be after start")
    try:
        results = earthaccess.search_data(
            short_name=short_name,
            bounding_box=bbox_wgs84,
            temporal=(start.isoformat(), (end_exclusive - timedelta(days=1)).isoformat()),
            count=2000,
        )
    except Exception as exc:
        raise FreshBeastError(f"HLS search failed for {short_name}: {exc}") from exc
    if len(results) == 2000:
        raise FreshBeastError(
            "HLS search returned the 2000-granule cap; narrow the AOI or date range"
        )
    return list(results)


def _window_for_bbox(
    dataset: rasterio.DatasetReader,
    bbox_wgs84: tuple[float, float, float, float],
) -> Window:
    """Compute a rounded pixel window for a WGS84 bbox."""
    left, bottom, right, top = transform_bounds(
        "EPSG:4326", dataset.crs, *bbox_wgs84, densify_pts=21
    )
    window = (
        from_bounds(left, bottom, right, top, dataset.transform)
        .round_offsets()
        .round_lengths()
    )
    if window.width <= 0 or window.height <= 0:
        raise FreshBeastError("AOI does not intersect the HLS tile")
    return window


def _select_bands(
    files: Iterable[Any], nir_band: str, swir_band: str
) -> dict[str, Any]:
    """Select NIR, SWIR2, and Fmask file handles from one granule."""
    wanted = {nir_band, swir_band, "Fmask"}
    selected: dict[str, Any] = {}
    for file in files:
        name = file.full_name
        for band in wanted:
            if name.endswith(f".{band}.tif"):
                selected[band] = file
    missing = wanted - set(selected)
    if missing:
        raise FreshBeastError(f"HLS granule is missing bands: {sorted(missing)}")
    return selected


def nbr_from_reflectance(
    nir_raw: np.ndarray,
    swir_raw: np.ndarray,
    fmask: np.ndarray,
    mask_bits: int = DEFAULT_MASK_BITS,
) -> np.ndarray:
    """Compute a cloud-masked NBR array.

    HLS surface reflectance is stored as scaled integers with -9999 as nodata.
    Bits in ``mask_bits`` are treated as invalid. The function does not apply a
    land-cover mask.
    """
    nir = nir_raw.astype(np.float64) * 0.0001
    swir = swir_raw.astype(np.float64) * 0.0001
    clear = (fmask.astype(np.uint8) & np.uint8(mask_bits)) == 0
    clear &= fmask != 255
    valid = clear & np.isfinite(nir) & np.isfinite(swir) & (nir > 0) & (swir > 0)
    denominator = nir + swir
    valid &= denominator > 0
    nbr = np.full(nir.shape, np.nan, dtype=np.float32)
    nbr[valid] = ((nir[valid] - swir[valid]) / denominator[valid]).astype(np.float32)
    return nbr


def _read_granule_nbr(
    granule: Any,
    short_name: str,
    bbox_wgs84: tuple[float, float, float, float],
    mask_bits: int,
) -> np.ndarray | None:
    """Read and compute NBR for one granule window."""
    nir_band, swir_band = SENSOR_BANDS[short_name]
    file_handles = earthaccess.open([granule])
    bands = _select_bands(file_handles, nir_band, swir_band)
    arrays: dict[str, np.ndarray] = {}
    window: Window | None = None
    try:
        for band in (nir_band, swir_band, "Fmask"):
            with rasterio.open(bands[band]) as dataset:
                if window is None:
                    window = _window_for_bbox(dataset, bbox_wgs84)
                arrays[band] = dataset.read(1, window=window)
        if len({array.shape for array in arrays.values()}) != 1:
            raise FreshBeastError("HLS bands did not share the same window shape")
        nbr = nbr_from_reflectance(
            arrays[nir_band], arrays[swir_band], arrays["Fmask"], mask_bits=mask_bits
        )
        return nbr if np.isfinite(nbr).any() else None
    finally:
        for file in file_handles:
            file.close()


def build_composites(
    bbox_wgs84: tuple[float, float, float, float],
    start: date,
    end_exclusive: date,
    *,
    workers: int = 4,
    mask_bits: int = DEFAULT_MASK_BITS,
    login_strategy: str = "netrc",
) -> tuple[CompositeStack, list[HlsGranule]]:
    """Build a regular 16-day mean NBR stack from public HLS.

    The output grid is the HLS grid intersected by ``bbox_wgs84``. A composite
    is the mean of valid NBR values in each 16-day bin; absent bins stay NaN.
    """
    if workers < 1:
        raise FreshBeastError("workers must be at least 1")
    login_earthdata(login_strategy)
    all_granules: list[tuple[Any, str]] = []
    for short_name in HLS_COLLECTIONS:
        for granule in search_hls(bbox_wgs84, start, end_exclusive, short_name):
            all_granules.append((granule, short_name))
    if not all_granules:
        raise FreshBeastError("no HLS granules found for the requested AOI and period")

    n_bins = math.ceil((end_exclusive - start).days / 16)
    if n_bins < 1:
        raise FreshBeastError("date range is too short for a 16-day composite")

    results: dict[int, list[np.ndarray]] = {}
    records: list[HlsGranule] = []
    errors: list[str] = []

    def read_one(item: tuple[Any, str]) -> tuple[int | None, HlsGranule, np.ndarray | None]:
        granule, short_name = item
        record = _granule_record(granule, short_name)
        acquired = _granule_date(granule)
        if acquired.date() < start or acquired.date() >= end_exclusive:
            return None, record, None
        offset = (acquired.date() - start).days
        bin_index = offset // 16
        nbr = _read_granule_nbr(granule, short_name, bbox_wgs84, mask_bits)
        return bin_index, record, nbr

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(read_one, item) for item in all_granules]
        for future in as_completed(futures):
            try:
                bin_index, record, nbr = future.result()
            except Exception as exc:
                errors.append(str(exc))
                continue
            records.append(record)
            if bin_index is not None and nbr is not None:
                results.setdefault(bin_index, []).append(nbr)

    if not results:
        detail = f" Last HLS error: {errors[-1]}" if errors else ""
        raise FreshBeastError(
            f"no clear HLS pixels were found in any composite.{detail}"
        )

    sample = next(iter(results.values()))[0]
    sums = np.zeros((n_bins, *sample.shape), dtype=np.float64)
    counts = np.zeros((n_bins, *sample.shape), dtype=np.int32)
    for bin_index, arrays in results.items():
        for nbr in arrays:
            if nbr.shape != sample.shape:
                raise FreshBeastError("HLS composites had inconsistent window shapes")
            valid = np.isfinite(nbr)
            sums[bin_index][valid] += nbr[valid]
            counts[bin_index][valid] += 1

    nbr_stack = np.full(sums.shape, np.nan, dtype=np.float32)
    has_data = counts > 0
    nbr_stack[has_data] = (sums[has_data] / counts[has_data]).astype(np.float32)

    # Re-open one granule for grid metadata. This is cheap and avoids carrying
    # a rasterio dataset outside the worker pool.
    first_granule, first_short_name = all_granules[0]
    handles = earthaccess.open([first_granule])
    try:
        first_band = SENSOR_BANDS[first_short_name][0]
        band = _select_bands(handles, *SENSOR_BANDS[first_short_name])[first_band]
        with rasterio.open(band) as dataset:
            crs = CRS.from_wkt(dataset.crs.to_wkt())
            window = _window_for_bbox(dataset, bbox_wgs84)
            transform = dataset.window_transform(window)
    finally:
        for file in handles:
            file.close()

    dates = np.asarray(
        [np.datetime64(start + timedelta(days=16 * index), "D") for index in range(n_bins)]
    )
    stack = CompositeStack(
        nbr=nbr_stack,
        counts=counts.astype(np.int16),
        dates=dates,
        crs=crs,
        transform=transform,
        bbox_wgs84=bbox_wgs84,
        start=start,
        end=end_exclusive,
        band_pairs=tuple(SENSOR_BANDS.values()),
        mask_bits=mask_bits,
    )
    records.sort(key=lambda record: (record.beginning_utc, record.native_id))
    return stack, records
