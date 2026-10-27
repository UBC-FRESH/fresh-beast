"""Run the reference Rbeast implementation on a composite stack."""

from __future__ import annotations

import contextlib
import csv
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .errors import FreshBeastError
from .io import CompositeStack

DEFAULT_THRESHOLD = 0.5


@dataclass(frozen=True)
class BeastConfig:
    """Configuration for a BEAST run.

    Attributes
    ----------
    threshold : float
        Minimum negative changepoint probability for an NSR detection.
    min_consecutive_years : int
        Number of consecutive annual probabilities above the threshold
        required before an event is emitted.
    r_libs_user : pathlib.Path | None
        Optional R library path containing ``Rbeast``.
    min_valid : int
        Minimum valid 16-day composites required before Rbeast is run. This
        guard prevents the reference C library from being called on very short
        or sparse series.
    """

    threshold: float = DEFAULT_THRESHOLD
    min_consecutive_years: int = 1
    r_libs_user: Path | None = None
    min_valid: int = 60


@dataclass(frozen=True)
class BeastOutput:
    """Validated BEAST output on the composite grid."""

    stack: CompositeStack
    config: BeastConfig
    time: np.ndarray
    cp_probability: np.ndarray
    negative_probability: np.ndarray
    trend: np.ndarray
    slope: np.ndarray
    summaries: dict[str, dict[str, object]]
    rbeast_version: str
    stdout: str
    stderr: str

    @property
    def shape(self) -> tuple[int, int, int]:
        """Return the probability-array shape."""
        return (
            int(self.negative_probability.shape[0]),
            int(self.negative_probability.shape[1]),
            int(self.negative_probability.shape[2]),
        )


def _rscript_path() -> str:
    """Return the Rscript executable or raise a useful error."""
    executable = shutil.which("Rscript")
    if executable is None:
        raise FreshBeastError(
            "Rscript was not found. Install R and the reference Rbeast package, "
            "then retry."
        )
    return executable


def _r_environment(r_libs_user: Path | None) -> dict[str, str]:
    """Return an environment that can load a user-library Rbeast."""
    environment = os.environ.copy()
    if r_libs_user is not None:
        environment["R_LIBS_USER"] = str(r_libs_user)
    elif "R_LIBS_USER" not in environment:
        default = Path.home() / "R" / "library"
        if default.exists():
            environment["R_LIBS_USER"] = str(default)
    return environment


def rbeast_version(r_libs_user: Path | None = None) -> str:
    """Return the installed Rbeast version."""
    result = subprocess.run(
        [
            _rscript_path(),
            "--vanilla",
            "-e",
            'cat(as.character(packageVersion("Rbeast")))',
        ],
        check=False,
        capture_output=True,
        text=True,
        env=_r_environment(r_libs_user),
    )
    if result.returncode != 0:
        raise FreshBeastError(
            "Rbeast is not available to Rscript. "
            "Install it with `install.packages(\"Rbeast\")`. "
            f"R stderr: {result.stderr.strip()[:500]}"
        )
    return result.stdout.strip()


def _decimal_years(dates: np.ndarray) -> np.ndarray:
    """Return a strictly regular decimal-year axis for the 16-day grid.

    Calendar dates are not exactly evenly spaced in decimal years because of
    leap years. BEAST requires a regular axis, so the first date is converted
    to decimal years and every later step is exactly 16/365.25 years. The
    original dates remain in ``CompositeStack`` for calendar-year grouping.
    """
    day_values = dates.astype("datetime64[D]")
    if day_values.size == 0:
        return np.asarray([], dtype=np.float64)
    first_year = int(day_values[0].astype("datetime64[Y]").astype(int)) + 1970
    first_start = day_values[0].astype("datetime64[Y]")
    first_day = int((day_values[0] - first_start).astype(int))
    start_decimal = first_year + first_day / 365.25
    return start_decimal + np.arange(day_values.size, dtype=np.float64) * 16.0 / 365.25


def _pixel_id(row: int, col: int) -> str:
    """Build a stable pixel id for the bridge CSV."""
    return f"p{row:04d}_{col:04d}"


def _write_wide_csv(
    path: Path,
    time: np.ndarray,
    nbr: np.ndarray,
    pixel_ids: dict[tuple[int, int], str],
) -> None:
    """Write one column per pixel for the R bridge."""
    rows, cols = nbr.shape[1], nbr.shape[2]
    header = ["time"] + [pixel_ids[(row, col)] for row in range(rows) for col in range(cols)]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for time_index, value in enumerate(time):
            row_values: list[object] = [f"{value:.10f}"]
            for row in range(rows):
                for col in range(cols):
                    item = nbr[time_index, row, col]
                    row_values.append("" if not np.isfinite(item) else f"{float(item):.8f}")
            writer.writerow(row_values)


def _read_summary(path: Path) -> dict[str, dict[str, object]]:
    """Read the bridge summary table."""
    summaries: dict[str, dict[str, object]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            pixel_id = row.get("pixel_id", "")
            if not pixel_id:
                continue
            summaries[pixel_id] = dict(row)
    return summaries


def _read_long(
    path: Path,
    time_axis: np.ndarray,
    pixel_ids: dict[tuple[int, int], str],
    shape: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Read the long BEAST table into arrays on the composite grid."""
    rows, cols = shape
    cp_probability = np.full((len(time_axis), rows, cols), np.nan, dtype=np.float32)
    negative_probability = np.full_like(cp_probability, np.nan)
    trend = np.full_like(cp_probability, np.nan)
    slope = np.full_like(cp_probability, np.nan)
    reverse_ids = {value: key for key, value in pixel_ids.items()}
    if not path.exists() or path.stat().st_size == 0:
        return cp_probability, negative_probability, trend, slope

    time0 = float(time_axis[0])
    delta = float(np.median(np.diff(time_axis))) if len(time_axis) > 1 else 1.0
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            pixel_id = row.get("pixel_id", "")
            if pixel_id not in reverse_ids:
                continue
            try:
                value_time = float(row["time"])
            except (KeyError, TypeError, ValueError):
                continue
            time_index = round((value_time - time0) / delta)
            if time_index < 0 or time_index >= len(time_axis):
                continue
            row_index, col_index = reverse_ids[pixel_id]
            for source, target in (
                ("cp_occ_pr", cp_probability),
                ("neg_cp_occ_pr", negative_probability),
                ("trend", trend),
                ("slope", slope),
            ):
                raw = row.get(source, "")
                if raw not in (None, ""):
                    with contextlib.suppress(TypeError, ValueError):
                        target[time_index, row_index, col_index] = float(raw)
    return cp_probability, negative_probability, trend, slope


def annual_negative_probability(
    output: BeastOutput,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return annual maximum negative changepoint probability.

    Returns
    -------
    years : numpy.ndarray
        Sorted integer years, shape ``(n_years,)``.
    probability : numpy.ndarray
        Annual maximum negative changepoint probability, shape
        ``(n_years, rows, cols)``.
    peak_index : numpy.ndarray
        Composite index of the annual peak, shape ``(n_years, rows, cols)``.
    """
    calendar = output.stack.dates.astype("datetime64[D]")
    years = calendar.astype("datetime64[Y]").astype(int) + 1970
    unique_years = np.unique(years)
    rows, cols = output.negative_probability.shape[1:]
    probability = np.full((len(unique_years), rows, cols), np.nan, dtype=np.float32)
    peak_index = np.full((len(unique_years), rows, cols), -1, dtype=np.int16)
    for year_index, year in enumerate(unique_years):
        indices = np.flatnonzero(years == year)
        if len(indices) == 0:
            continue
        block = output.negative_probability[indices]
        finite = np.isfinite(block)
        local_peak = np.argmax(np.where(finite, block, -np.inf), axis=0)
        any_finite = finite.any(axis=0)
        grid = np.indices(block.shape[1:])
        probability[year_index][any_finite] = block[
            local_peak, grid[0], grid[1]
        ][any_finite]
        peak_index[year_index][any_finite] = indices[local_peak][any_finite]
    return unique_years, probability, peak_index


def run_rbeast(stack: CompositeStack, config: BeastConfig | None = None) -> BeastOutput:
    """Run Rbeast on every pixel with at least ten valid composites."""
    config = config or BeastConfig()
    if not 0 < config.threshold <= 1:
        raise FreshBeastError("threshold must be in (0, 1]")
    if config.min_consecutive_years < 1:
        raise FreshBeastError("min_consecutive_years must be at least 1")
    if config.min_valid < 10:
        raise FreshBeastError("min_valid must be at least 10")

    version = rbeast_version(config.r_libs_user)
    script = Path(__file__).with_name("R") / "beast_bridge.R"
    if not script.exists():
        raise FreshBeastError(f"R bridge is missing: {script}")

    time = _decimal_years(stack.dates)
    pixel_ids = {
        (row, col): _pixel_id(row, col)
        for row in range(stack.nbr.shape[1])
        for col in range(stack.nbr.shape[2])
    }
    if not np.isfinite(stack.nbr).any():
        raise FreshBeastError("composite stack has no finite NBR values")

    with tempfile.TemporaryDirectory(prefix="fresh-beast-") as temporary:
        temporary_path = Path(temporary)
        input_path = temporary_path / "nbr_wide.csv"
        summary_path = temporary_path / "beast_summary.csv"
        long_path = temporary_path / "beast_long.csv"
        _write_wide_csv(input_path, time, stack.nbr, pixel_ids)
        result = subprocess.run(
            [
                _rscript_path(),
                "--vanilla",
                str(script),
                "--input",
                str(input_path),
                "--summary",
                str(summary_path),
                "--long",
                str(long_path),
                "--min-valid",
                str(config.min_valid),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=_r_environment(config.r_libs_user),
        )
        if result.returncode != 0:
            raise FreshBeastError(
                "Rbeast bridge failed. "
                f"stdout: {result.stdout.strip()[:1000]} "
                f"stderr: {result.stderr.strip()[:1000]}"
            )
        summaries = _read_summary(summary_path)
        cp_probability, negative_probability, trend, slope = _read_long(
            long_path, time, pixel_ids, stack.nbr.shape[1:]
        )

    return BeastOutput(
        stack=stack,
        config=config,
        time=time,
        cp_probability=cp_probability,
        negative_probability=negative_probability,
        trend=trend,
        slope=slope,
        summaries=summaries,
        rbeast_version=version,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def annual_probability_rows(output: BeastOutput) -> list[dict[str, object]]:
    """Flatten annual negative probabilities into CSV-ready rows."""
    years, probability, peak_index = annual_negative_probability(output)
    rows: list[dict[str, object]] = []
    for year_index, year in enumerate(years):
        for row in range(probability.shape[1]):
            for col in range(probability.shape[2]):
                value = probability[year_index, row, col]
                if not np.isfinite(value):
                    continue
                pixel_index = int(peak_index[year_index, row, col])
                rows.append(
                    {
                        "year": int(year),
                        "row": row,
                        "col": col,
                        "pixel_id": _pixel_id(row, col),
                        "negative_cp_probability": float(value),
                        "peak_time": float(output.time[pixel_index]) if pixel_index >= 0 else None,
                    }
                )
    return rows


def write_annual_probability_csv(output: BeastOutput, path: Path) -> None:
    """Write the annual probability table."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = annual_probability_rows(output)
    fieldnames = ["year", "row", "col", "pixel_id", "negative_cp_probability", "peak_time"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def beast_summary(output: BeastOutput) -> dict[str, object]:
    """Return a compact JSON-safe BEAST summary."""
    statuses: dict[str, int] = {}
    for summary in output.summaries.values():
        status = str(summary.get("status", "unknown"))
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "rbeast_version": output.rbeast_version,
        "time_steps": int(output.time.size),
        "pixels": int(output.negative_probability.shape[1] * output.negative_probability.shape[2]),
        "pixels_with_summary": len(output.summaries),
        "status_counts": statuses,
        "threshold": output.config.threshold,
        "min_consecutive_years": output.config.min_consecutive_years,
        "min_valid": output.config.min_valid,
        "season": "harmonic",
        "period_years": 1.0,
    }


def write_beast_pixels_csv(output: BeastOutput, path: Path) -> None:
    """Write per-pixel, per-composite BEAST probabilities."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "pixel_id",
        "time",
        "year",
        "cp_occ_pr",
        "neg_cp_occ_pr",
        "trend",
        "slope",
    ]
    rows, cols = output.negative_probability.shape[1:]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for time_index, value_time in enumerate(output.time):
            year = int(output.stack.dates[time_index].astype("datetime64[Y]").astype(int)) + 1970
            for row in range(rows):
                for col in range(cols):
                    negative = output.negative_probability[time_index, row, col]
                    cp_value = output.cp_probability[time_index, row, col]
                    if not np.isfinite(negative) and not np.isfinite(cp_value):
                        continue
                    writer.writerow(
                        {
                            "pixel_id": _pixel_id(row, col),
                            "time": f"{value_time:.10f}",
                            "year": year,
                            "cp_occ_pr": f"{cp_value:.8f}" if np.isfinite(cp_value) else "",
                            "neg_cp_occ_pr": f"{negative:.8f}" if np.isfinite(negative) else "",
                            "trend": (
                                f"{output.trend[time_index, row, col]:.8f}"
                                if np.isfinite(output.trend[time_index, row, col])
                                else ""
                            ),
                            "slope": (
                                f"{output.slope[time_index, row, col]:.8f}"
                                if np.isfinite(output.slope[time_index, row, col])
                                else ""
                            ),
                        }
                    )
