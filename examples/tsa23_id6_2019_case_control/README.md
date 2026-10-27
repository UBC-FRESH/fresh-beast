# TSA 23 2019 ID6 case-control validation

This is the first **case-control** test of `fresh-beast` against a historical
AOS polygon. It is a deliberately small validation sample, not a provincial
accuracy estimate.

## Label

- AOS polygon `19542019`
- capture year `2019`
- agent `ID6`, Aspen Leaf Miner
- severity `Moderate`
- polygon area `1,080.07 ha`

The 68 × 57 HLS window contains 90 TSA 23 blocks:

| Class | Rule | Blocks |
|---|---|---:|
| Positive | ≥99% of block area inside the AOS polygon | 31 |
| Control | ≤0.1% of block area inside the polygon | 47 |
| Excluded | partial boundary overlap | 12 |

The 12 boundary blocks are excluded so edge contamination does not decide the
result.

## Run

```bash
fresh-beast composites \
  --bbox -121.47705396020223 51.492802825635046 \
         -121.45305396020223 51.51080282563505 \
  --start 2013-01-01 --end 2020-12-31 \
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
| HLS granules | 924 |
| Composite stack | 183 × 68 × 57, 30 m |
| Finite composite fraction | 0.403 |
| Rbeast version | 1.0.2 |
| Pixels processed | 3,876 / 3,876 |
| Threshold | 0.5 negative changepoint probability |
| Events | 37 across 32 blocks |
| Event area | 7.29 ha |

Primary detection window: **2018–2020**, around the 2019 AOS capture.

| Metric | Value |
|---|---:|
| True positives | 8 |
| False positives | 16 |
| False negatives | 23 |
| True negatives | 31 |
| Sensitivity | **25.8%** |
| Specificity | **66.0%** |
| Precision | **33.3%** |
| Accuracy | **50.0%** |

Same-year only (2019): **0/31** positives detected, **0/47** controls flagged.

Most events are in 2018: 31 of 37. That is one year before the 2019 AOS capture,
but 16 of 47 control blocks also have 2018 events, so the early timing does not
rescue the result.

## Verdict

**Do not promote this detector to operational use at the 0.5 threshold for
ID6.** The case-control result shows both low sensitivity and substantial false
positives in this window.

This is not evidence that BEAST is universally unusable. It is evidence that
the current HLS-only, 0.5-threshold configuration is not validated for moderate
Aspen Leaf Miner in TSA 23. A different threshold, index, label severity, or
land-cover mask would be a new model decision and must not be selected on these
same labels without an independent validation set.

The event table is still consumable:

```text
femic.contracts.disturbance.validate_disturbance_event: 37/37 valid
ws4 disturbance --events events.json
37 events  years: 2013-2020  blocks: 32
```

`validation_case_control.json` contains the full metrics and caveats. No WS4
objective, growth, constraint, or solver code was changed.
