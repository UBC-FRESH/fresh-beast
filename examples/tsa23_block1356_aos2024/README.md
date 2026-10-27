# TSA 23 block 1356 / 2024 AOS cluster pilot

This is the first **positive-label cluster** for `fresh-beast`. It uses the
archived all-years BC Pest Infestation Polygons layer (the historical AOS
geodatabase), not only the 2025 current layer.

## Label

- AOS polygon `154262024`
- capture year `2024`
- agent `IDW`, Western Spruce Budworm
- severity `Severe`
- polygon area `28,888.56 ha`
- 20 TSA 23 blocks in the 1.1 km HLS window intersect the polygon
- total block area `275.89 ha`

The AOS label is an agent/severity label. BEAST detects an NBR changepoint; it
does not attribute the agent or assign severity.

## Data and run

```bash
fresh-beast composites \
  --bbox -121.62084 51.08985 -121.60484 51.09985 \
  --start 2013-01-01 --end 2025-12-31 \
  --out hls_composites.npz \
  --provenance hls_granules.json \
  --workers 6

fresh-beast detect \
  --composites hls_composites.npz \
  --blocks blocks_all.geojson \
  --out-dir .
```

| Item | Value |
|---|---|
| HLS granules | 1,174 (L30 650, S30 524) |
| Composite period | 2013-01-01 to 2025-12-31, 16-day bins |
| Composite stack | 297 × 38 × 38, 30 m, UTM 10N |
| Finite composite fraction | 0.504 |
| Rbeast version | 1.0.2 |
| Pixels processed | 1,444 / 1,444 |
| Detection threshold | 0.5 negative changepoint probability |
| Blocks with any event | **19 / 20** |
| Total events | **60** |
| Event area | 74.16 ha across 275.89 ha of blocks |
| Same-year 2024 event | 7 blocks |
| 2023 event (one year early) | 18 blocks |
| 2023-only early event | 12 blocks |
| No event | block `98831` |

The 19/20 block-level sensitivity is **2.3 percentage points** below full
coverage. Twelve blocks have a 2023 event but no 2024 event; those are reported
as early detections, not same-year agreement.

Block `1356` itself has events in **2018, 2020, and 2023**; the latest is one
year before the 2024 AOS capture.

## What this establishes

- The package can consume archived historical AOS labels, not just the current
  year layer.
- It produces real `femic.disturbance.v1` records on a 20-block positive
  cluster.
- The full event table passes FEMIC validation (60/60) and WS4's consumer:

```text
ws4 disturbance --events events_all.json --block-id 1356
events: 3  years: 2018-2023  blocks: 1
```

## What it does not establish

- **No false-positive estimate.** All 20 blocks in the HLS window are inside
  the 2024 AOS polygon. A case-control sample is still required.
- AOS has omission and commission error and is not a pixel-level truth set.
- BEAST has no agent or severity mapping; `IDW` is the AOS label, not a BEAST
  classification.
- Several blocks have earlier events (2013–2021) whose causes are unverified.
- The 2023 events are early detections; they are not same-year agreement.
- One block (`98831`) had no event at the 0.5 threshold.

`validation_cluster.json` records the full block-level metrics and caveats.
`events_all.json` is the 60-event table. The CLI also writes
`beast_pixels.csv`; the 32 MB per-composite file is omitted from the repository
and can be regenerated with the commands above.
