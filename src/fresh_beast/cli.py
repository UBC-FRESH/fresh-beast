"""Command-line entry point for fresh-beast."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from . import __version__
from .beast import (
    BeastConfig,
    run_rbeast,
    write_annual_probability_csv,
    write_beast_pixels_csv,
)
from .events import actions_to_events, write_outputs
from .hls import build_composites
from .io import CompositeStack, write_json


def _parse_date(value: str) -> date:
    """Parse an ISO date."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date: {value!r}") from exc


def _add_bbox(parser: argparse.ArgumentParser) -> None:
    """Add the shared WGS84 bbox argument."""
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        required=True,
        metavar=("MINX", "MINY", "MAXX", "MAXY"),
        help="AOI in EPSG:4326",
    )


def _composites(args: argparse.Namespace) -> int:
    """Build and save an HLS composite stack."""
    minx, miny, maxx, maxy = args.bbox
    if minx >= maxx or miny >= maxy:
        raise SystemExit("bbox must be ordered minx miny maxx maxy")
    start = args.start
    end_exclusive = args.end + timedelta(days=1)
    stack, records = build_composites(
        (minx, miny, maxx, maxy),
        start,
        end_exclusive,
        workers=args.workers,
        login_strategy=args.earthdata_login,
    )
    stack.save(args.out)
    write_json(
        args.provenance,
        {
            "schema_version": "fresh.beast.hls-granules.v1",
            "retrieved_utc": datetime.now(UTC).isoformat(),
            "source": "NASA HLS L30/S30 v2 via earthaccess",
            "bbox_wgs84": [minx, miny, maxx, maxy],
            "start": start.isoformat(),
            "end_inclusive": args.end.isoformat(),
            "composite_days": 16,
            "mask_bits": stack.mask_bits,
            "band_pairs": [list(pair) for pair in stack.band_pairs],
            "granules": [record.to_dict() for record in records],
        },
    )
    print(
        f"wrote {args.out} shape={stack.shape} valid_fraction={stack.valid_fraction:.3f} "
        f"granules={len(records)}"
    )
    return 0


def _detect(args: argparse.Namespace) -> int:
    """Run BEAST and write events/results."""
    stack = CompositeStack.load(args.composites)
    config = BeastConfig(
        threshold=args.threshold,
        min_consecutive_years=args.min_consecutive_years,
        r_libs_user=args.r_libs_user,
        min_valid=args.min_valid,
    )
    print(f"running Rbeast on {stack.shape[1] * stack.shape[2]} pixels")
    output = run_rbeast(stack, config)
    write_annual_probability_csv(output, args.out_dir / "annual_probability.csv")
    write_beast_pixels_csv(output, args.out_dir / "beast_pixels.csv")
    events = actions_to_events(output, args.blocks)
    paths = write_outputs(
        output,
        events,
        args.out_dir,
        aoi_source=str(args.composites),
        block_source=str(args.blocks),
    )
    print(
        f"wrote {paths['events']} ({len(events)} events), {paths['result']}, "
        f"and {args.out_dir / 'annual_probability.csv'}"
    )
    return 0


def _version(_: argparse.Namespace) -> int:
    """Print the package version."""
    print(__version__)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="fresh-beast",
        description="HLS/BEAST NSR detection for FEMIC and WS4",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    composites = subparsers.add_parser(
        "composites", help="build 16-day HLS NBR composites"
    )
    _add_bbox(composites)
    composites.add_argument("--start", type=_parse_date, required=True)
    composites.add_argument("--end", type=_parse_date, required=True)
    composites.add_argument("--out", type=Path, required=True)
    composites.add_argument("--provenance", type=Path, required=True)
    composites.add_argument("--workers", type=int, default=4)
    composites.add_argument(
        "--earthdata-login",
        default="netrc",
        help="earthaccess login strategy (default: netrc)",
    )
    composites.set_defaults(func=_composites)

    detect = subparsers.add_parser(
        "detect", help="run BEAST and emit femic.disturbance.v1 events"
    )
    detect.add_argument("--composites", type=Path, required=True)
    detect.add_argument("--blocks", type=Path, required=True)
    detect.add_argument("--out-dir", type=Path, required=True)
    detect.add_argument("--threshold", type=float, default=0.5)
    detect.add_argument("--min-consecutive-years", type=int, default=1)
    detect.add_argument("--min-valid", type=int, default=60)
    detect.add_argument("--r-libs-user", type=Path, default=None)
    detect.set_defaults(func=_detect)

    version = subparsers.add_parser("version", help="print the version")
    version.set_defaults(func=_version)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:  # keep CLI failures concise and actionable
        print(f"fresh-beast: {exc}", file=sys.stderr)
        return 1
