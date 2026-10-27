# TSA 23 block 1356 / 2025 AOS label

This is the first **positive-label** pilot for `fresh-beast`. It uses a real
BC Aerial Overview Survey (AOS) polygon from the 2025 current Pest Infestation
Polygons layer:

- AOS polygon `194132025`
- agent `IDW`, Western Spruce Budworm
- severity `Severe`
- capture year `2025`
- polygon area `1,832.81 ha`
- TSA 23 block `1356` is fully inside the polygon (`10.23 ha`)

The AOS label is an **agent/severity label**, not a BEAST label. BEAST detects
an NBR changepoint; it does not attribute the agent.

## Commands

```bash
fresh-beast composites \
  --bbox -121.62084 51.08985 -121.60484 51.09985 \
  --start 2013-01-01 --end 2025-12-31 \
  --out hls_composites.npz \
  --provenance hls_granules.json \
  --workers 6

fresh-beast detect \
  --composites hls_composites.npz \
  --blocks blocks.geojson \
  --out-dir .
```

## Result

| Item | Value |
|---|---|
| HLS granules | 1,174 (L30 650, S30 524) |
| Composite period | 2013-01-01 to 2025-12-31, 16-day bins |
| Composite stack | 297 × 38 × 38, 30 m, UTM 10N |
| Finite composite fraction | 0.504 |
| Rbeast version | 1.0.2 |
| Pixels processed | 1,444 / 1,444 |
| Detection threshold | 0.5 negative changepoint probability |
| Events in block 1356 | **2** |
| 2018 event | 0.63 ha, 7 pixels, confidence 0.585 |
| 2023 event | 6.84 ha, 76 pixels, confidence 0.996 |
| 2025 annual max in block | 0.469 (below threshold) |

The **2023** event precedes the 2025 AOS capture by two years. That is
consistent with early detection of a developing defoliation event, but it is
not same-year agreement. The **2018** event is seven years before the AOS
capture; its cause is not attributed, and it may be a separate or false
positive. The 2025 AOS label itself did not produce a 2025 event at the 0.5
threshold.

`validation.json` records the block/label overlap, event years, event areas,
lead time, and caveats. The block is fully inside the AOS polygon; the label
intersection is 10.23 ha.

The event table also passed both consumers:

```text
femic.contracts.disturbance.validate_disturbance_event: 2/2 valid
ws4 disturbance --events events.json --block-id 1356
events: 2  years: 2018-2023  blocks: 1
```

## Interpretation

This pilot is evidence that the package can produce real `femic.disturbance.v1`
events on a labelled block. It is not a formal accuracy assessment:

- the AOS label is 2025, while the Brown et al. reference period is 2002–2020;
- AOS has omission and commission error, and is not a pixel-level truth set;
- BEAST has no agent or severity mapping;
- one block is not a validation sample.

A proper validation needs a stratified AOS sample over the full period and
multiple disturbance agents, with omission and commission reported separately.
