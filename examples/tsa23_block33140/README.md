# TSA 23 block 33140 pilot

This directory is the first real-data exercise of `fresh-beast`. It is a
**negative-control / pipeline pilot**, not a claim that TSA 23 block 33140 has
an NSR.

## Commands

```bash
fresh-beast composites \
  --bbox -121.23817787392457 51.56845850074679 \
         -121.22617787392457 51.57645850074679 \
  --start 2013-01-01 --end 2020-12-31 \
  --out hls_composites.npz \
  --provenance hls_granules.json \
  --workers 6

fresh-beast detect \
  --composites hls_composites.npz \
  --blocks blocks.geojson \
  --out-dir .
```

`blocks.geojson` is a single-block extract from the TSA 23 instance block
layer. The AOI is a 1 km window around block 33140 (9.62 ha).

## Result (2026-10-27)

| Item | Value |
|---|---|
| HLS granules | 636 (L30 279, S30 357) |
| HLS composite period | 2013-01-01 to 2020-12-31, 16-day bins |
| Composite stack | 183 x 30 x 28, 30 m, UTM 10N |
| Finite composite fraction | 0.444 |
| Rbeast version | 1.0.2 |
| Pixels with BEAST result | 840 / 840 |
| Detection threshold | 0.5 negative changepoint probability |
| Events | **0** |
| Maximum negative probability inside block | 0.348 (2017) |

The block contains 114 fully covered 30 m pixels. No pixel-year inside the
block reached the 0.5 threshold, so no `femic.disturbance.v1` event was
emitted. This is a valid negative result for this block; it is not evidence
that BEAST cannot detect NSR elsewhere.

## What this demonstrates

- Public HLS L30/S30 granules were opened through Earthdata without bulk
  downloading; only the 1 km window was read.
- NBR, Fmask masking, 16-day composites, Rbeast, and block aggregation ran on
  real data.
- The result is a no-detection control with a complete 840-pixel BEAST run.

## What it does not demonstrate

- No AOS polygon validation was performed.
- No agent or severity attribution is claimed.
- HLS-only data starts in 2013; Brown et al. used Landsat from 2000.
- No positive real NSR event is present in this example. The event-contract
  path is covered by `tests/test_events.py` and `tests/test_consumers.py`.

See `result.json` for the exact method and caveat block, `hls_granules.json`
for every granule id, and `annual_probability.csv` /
`beast_pixels.csv` for the per-pixel diagnostics.
