# Why `fresh-beast`, how it fits FRESH, and what happens next

Status: **alpha / operational use deferred**  
Last updated: 2026-10-28

## Why we built it

FRESH already had a shared language for disturbances:

- FEMIC owns `femic.disturbance.v1`.
- WS4 can read and report those events.
- The contract explicitly includes `partial_mortality` for non-stand-replacing
  disturbances.

What the ecosystem did **not** have was a reproducible way to turn a public
satellite time series into those events. The gap was an implementation and
provenance gap, not a missing contract.

The published Brown et al. (2025) workflow is a good fit for the first attempt:

- public HLS L30/S30 surface reflectance at 30 m;
- NBR from NIR and SWIR2;
- 16-day NBR composites;
- BEAST change detection through the reference `Rbeast` implementation;
- annual changepoint-probability surfaces that can be aggregated to stands.

`fresh-beast` was built as a separate package because it is an experimental
remote-sensing detector, not a reason to put HLS access, Earthdata credentials,
R, `Rbeast`, and research thresholds into the FEMIC or WS4 runtime. Keeping it
separate also keeps the GPL `Rbeast` dependency out of the core packages.

The package does **not** re-derive BEAST. Brown et al. use `Rbeast` but do not
publish the exact MCMC argument list or a BEAST-to-severity mapping.
`fresh-beast` therefore wraps the reference implementation, records the installed
`Rbeast` version, and exposes the uncertainty instead of inventing coefficients.

## What the package does

```text
HLS L30/S30
    |
    |  windowed reads through Earthdata
    v
Fmask + NBR: (NIR - SWIR2) / (NIR + SWIR2)
    |
    |  16-day mean composites
    v
Rbeast / BEAST
    |
    |  annual negative changepoint probability
    v
block aggregation
    |
    v
femic.disturbance.v1
    |
    +--> FEMIC contract validation
    +--> WS4 disturbance report
    +--> fresh.beast.v1 provenance
```

Key implementation choices:

- HLS L30 bands `B05`/`B07`; S30 bands `B8A`/`B12`.
- Fmask bits 0–4 and fill value 255 are masked.
- `Rbeast` uses harmonic seasonality and an annual period.
- The default detector threshold is `0.5` negative changepoint probability,
  taken from Mulverhill et al. (2023), not invented here.
- A stability guard skips series with fewer than 60 valid composites.
- Events are `partial_mortality`; the package does **not** attribute an agent
  or assign an AOS severity class.
- No forest/non-forest mask (for example NTEMS VLCE) is applied by the package;
  that is the caller's responsibility.

## What the evidence says

Three real-data pilots were run.

### 1. Negative control

`examples/tsa23_block33140/`

- HLS 2013–2020
- 636 granules, 183 composites
- 840/840 pixels processed
- 0 events at threshold 0.5
- maximum in-block probability 0.348

This shows the pipeline can run on real data without producing an event.

### 2. Positive-label cluster, no controls

`examples/tsa23_block1356_aos2024/`

- 2024 AOS polygon `154262024`
- `IDW` Western Spruce Budworm, Severe
- 20 TSA 23 blocks inside the polygon
- 1,174 HLS granules, 297 composites, 1,444 pixels
- 60 events
- 19/20 blocks have an event
- 18 blocks have a 2023 event, one year before the 2024 AOS capture

This is a positive-label cluster, not an accuracy estimate: all 20 blocks are
inside the AOS polygon, so it says nothing about false positives.

### 3. Case-control validation

`examples/tsa23_id6_2019_case_control/`

- 2019 AOS polygon `19542019`
- `ID6` Aspen Leaf Miner, Moderate
- 31 fully positive blocks
- 47 control blocks
- 12 boundary blocks excluded
- 924 HLS granules, 183 composites, 3,876 pixels
- 37 events

Primary window 2018–2020:

| Metric | Value |
|---|---:|
| True positives | 8 |
| False positives | 16 |
| False negatives | 23 |
| True negatives | 31 |
| Sensitivity | 25.8% |
| Specificity | 66.0% |
| Precision | 33.3% |
| Accuracy | 50.0% |

Same-year 2019 detection was 0/31.

**Result: the 0.5 detector is not validated for operational ID6 use.**

The earlier 2024 cluster is not a rescue. It had no controls, so its apparent
19/20 success cannot establish specificity.

## Decision

DIS-02 is **deferred for operational use**. The package is retained as:

- a reproducible implementation of a published workflow;
- a source of `femic.disturbance.v1` event tables for exploratory analysis;
- a negative validation result that prevents overclaiming.

It must not be attached to:

- FEMIC growth or yield assumptions;
- WS4 objectives, constraints, or solver logic;
- operational scheduling decisions.

## How it plugs into FRESH

### FEMIC

FEMIC owns the contract and the validator.

- `fresh-beast` emits full `femic.disturbance.v1` records.
- FEMIC's `validate_disturbance_event` accepts the emitted records.
- Events carry `block_ids` so they can be joined to WS4 blocks.
- `fresh-beast` is **not** a FEMIC runtime dependency.
- No FEMIC growth, yield, or objective code was changed.

The current event shape is intentionally conservative:

- `event_type = partial_mortality`
- `severity_class = unknown`
- `severity_value = null`
- agent attribution is absent
- `confidence` is the BEAST changepoint probability, not an AOS accuracy

### WS4

WS4 is the consumer/reporting surface.

- `ws4.disturbance.load_disturbance_events` reads the event table.
- `ws4 disturbance --events ...` summarizes the events.
- Events can be filtered to a block id.
- WS4 currently treats them as **informational**; they do not change the
  simulator, growth curves, objective, constraints, or solver.
- No WS4 production code was changed by this work.

### Nemora and FHOPS

There is no direct integration today.

- Nemora could consume the same event table if an inventory or sampling workflow
  needs stand-level disturbance history, but no such dependency exists.
- FHOPS could later consume events as an operational context layer, but that is
  out of scope until validation supports it.
- The shared contract is the interface; the detector package is not.

### External dependencies

- NASA Earthdata / HLS for imagery.
- R and `Rbeast` for the reference BEAST implementation.
- BC Aerial Overview Survey (AOS) for labels.
- No credentials are stored in the repository.

## What we plan to do

### Now

- Keep DIS-02 deferred.
- Keep the package public and reproducible.
- Fix packaging, provenance, and test coverage only; do not tune the detector
  against the failed case-control labels.

### If the work is reopened

The next defensible step is an **independent held-out validation**, not a
threshold search on the same data:

1. Choose different AOS polygons, agents, and years.
2. Freeze the 0.5 threshold and current preprocessing.
3. Report sensitivity, specificity, precision, and lead time by agent/severity.
4. Only then decide whether an alternate index, threshold, or forest mask is
   justified.
5. Calibrate any alternate detector on a separate set and validate once on a
   held-out set.

Other possible work, in priority order:

- add Landsat 2000–2015 composites to match the Brown et al. time span;
- add an explicit forest/non-forest mask;
- add AOS severity/agent joins without turning them into BEAST outputs;
- add a report-only FEMIC/WS4 integration if a validated use case appears.

### What would make it operational

Not “more events” and not a lower threshold. Operational use would require:

- independent validation with acceptable sensitivity and specificity;
- stated performance by agent, severity, and region;
- an explicit management decision about how partial-mortality events affect
  growth, risk, or scheduling;
- a change proposal for FEMIC/WS4 rather than a silent package-side change.

## Reopen criteria

DIS-02 should stay deferred until all of these are true:

- an independent AOS sample exists;
- the 0.5 baseline is evaluated without tuning on that sample;
- a held-out validation result is available;
- the intended use is defined (report-only, risk screen, or growth input);
- the owning package accepts the semantic change.

Until then, `fresh-beast` is a research and provenance tool, not a production
disturbance layer.
