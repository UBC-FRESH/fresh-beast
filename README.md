# fresh-beast

`fresh-beast` is an open-source Python package that turns Harmonized Landsat
Sentinel-2 (HLS) surface-reflectance time series into BEAST change-probability
rasters and `femic.disturbance.v1` non-stand-replacing (NSR) events for the
FRESH modelling ecosystem.

It is deliberately a **detector adapter**, not a new disturbance model. The
change detection is the published BEAST algorithm, run through the reference
`Rbeast` implementation, with the processing choices reported in Brown et al.
(2025) where those choices are stated. Where the paper does not publish a
choice (for example, exact MCMC settings or an NSR severity mapping), this
package exposes the gap rather than inventing a coefficient.

> Status: `0.1.0a1` alpha. The package has been exercised on a TSA 23
> negative-control pilot; it is not yet a province-wide production detector and
> has not been validated against AOS polygons.

## What it does

1. Searches and opens public HLS L30/S30 granules through NASA Earthdata
   (`earthaccess`).
2. Reads only the requested window, masks cloud/cloud-shadow/snow/water pixels
   with the HLS `Fmask`, and computes NBR from
   `(NIR - SWIR2) / (NIR + SWIR2)`.
3. Builds regular 16-day mean NBR composites.
4. Runs BEAST (`Rbeast`, harmonic seasonality, annual period) on each pixel.
5. Converts negative changepoint probability into annual NSR detections and
   aggregates them to FEMIC/WS4 block ids.
6. Writes a `fresh.beast.v1` result and a `femic.disturbance.v1` event table.

It does **not** attribute an agent (insect, wind, drought), assign a published
severity class, or replace the FEMIC/WS4 disturbance consumer. A BEAST
detection is `partial_mortality`; the agent is unknown unless another source
supplies it.

## Install

`fresh-beast` needs Python 3.11+ and an R installation with the reference
`Rbeast` package. `Rbeast` is GPL-2/GPL-3 and is installed separately; this
package does not vendor it.

```bash
python -m pip install -e ".[dev]"

# Earthdata credentials, normally in ~/.netrc (mode 600):
# machine urs.earthdata.nasa.gov
#   login YOUR_USERNAME
#   password YOUR_PASSWORD

Rscript -e 'install.packages("Rbeast", repos="https://cloud.r-project.org")'
```

`fresh-beast` uses `R_LIBS_USER` when it invokes `Rscript`, so a user-library
install such as `/home/user/R/library` works.

## Run the pilot

```bash
fresh-beast composites \
  --bbox -121.23817787392457 51.56845850074679 \
         -121.22617787392457 51.57645850074679 \
  --start 2013-01-01 --end 2020-12-31 \
  --out examples/tsa23_block33140/hls_composites.npz \
  --provenance examples/tsa23_block33140/hls_granules.json \
  --workers 4

fresh-beast detect \
  --composites examples/tsa23_block33140/hls_composites.npz \
  --blocks /path/to/tsa23_blocks.geojson \
  --out-dir examples/tsa23_block33140
```

Outputs:

| File | Meaning |
|---|---|
| `hls_composites.npz` | 16-day NBR array, observation counts, dates, CRS/transform, AOI |
| `hls_granules.json` | exact HLS granule ids, acquisition times, collection ids |
| `beast_pixels.csv` | per-pixel BEAST changepoint probabilities and NBR step |
| `events.json` | `femic.disturbance.v1` event table |
| `result.json` | `fresh.beast.v1` method, provenance, summary, and caveats |
| `annual_probability.csv` | annual maximum negative changepoint probability per pixel |

## Method choices

The Brown et al. (2025) workflow is the reference:

- HLS L30/S30 surface reflectance, 30 m.
- NBR from NIR and SWIR2.
- 16-day mean composites of valid (cloud/snow/water-masked) pixels.
- BEAST through `Rbeast`, harmonic seasonal component.
- Annual negative changepoint probability used as the NSR signal.
- Detection threshold `0.5` is the published near-real-time BEAST threshold
  from Mulverhill et al. (2023); it is configurable, not a universal constant.
- A stability guard skips series with fewer than 60 valid composites
  (`--min-valid`); this is not a paper coefficient.

The paper reports Rbeast and its spin-up design but does not publish the exact
`Rbeast` argument list, MCMC settings, or an NSR severity mapping. This package
therefore:

- keeps `Rbeast` defaults unless an argument is required for the 16-day time
  axis;
- sets `season="harmonic"`, `period=1 year`, and `deltat=16/365.25` so the
  regular 16-day series is interpreted in decimal years;
- records the Rbeast version and all arguments in `result.json`;
- leaves `severity_class="unknown"` and `severity_value=null`, with the NBR step
  in `notes`, rather than inventing low/moderate/high classes.

This is a data-contract-first implementation. It does not claim that a BEAST
event is a specific insect or a specific AOS severity class.

## Integration

The package emits the same event shape consumed by FEMIC and WS4:

```json
{
  "schema_version": "femic.disturbance.v1",
  "event_id": "fresh-beast:33140:2018:neg-change",
  "event_type": "partial_mortality",
  "year": 2018,
  "severity_class": "unknown",
  "severity_value": null,
  "severity_basis": "BEAST negative NBR changepoint; no published severity mapping",
  "confidence": 0.86,
  "attribution": "BEAST/Rbeast",
  "attribution_method": "Rbeast harmonic changepoint probability, negative NBR trend",
  "block_ids": [33140],
  "area_ha": 8.1,
  "source_id": "hls-beast-nsr",
  "source_version": "fresh-beast 0.1.0a1",
  "retrieved_utc": "2026-10-27T00:00:00+00:00",
  "notes": "..."
}
```

Downstream, the existing WS4 reader validates the flat consumer fields and
FEMIC validates the full event. The package does not modify either consumer.

## Data and coverage caveats

- HLS starts in 2013 for L30 and 2015 for S30. This package currently builds
  HLS-only composites, so a 2013 start has only two years of pre-period before
  the 2015+ S30 record; Brown et al. used Landsat from 2000.
- A BEAST probability is a changepoint probability, not a probability that a
  specific agent caused the change, and not a tree-survival estimate.
- The pilot is not a validation against BC Aerial Overview Survey polygons.
  Validation labels must be joined separately and reported separately.
- HLS `Fmask` bits 0-4 are treated as cloud, adjacent cloud, cloud shadow,
  snow/ice, and water. The mask is recorded in provenance; it is not tuned.
- The land-cover mask used by Brown et al. (NTEMS VLCE) is not applied by this
  package. Forest/non-forest masking is the caller's responsibility.

## References

- Brown, M. S., Coops, N. C., Mulverhill, C., & Achim, A. (2025).
  Detection of non-stand replacing disturbances (NSR) using Harmonized
  Landsat-Sentinel-2 time series. *ISPRS Journal of Photogrammetry and Remote
  Sensing*, 220, 264-276. https://doi.org/10.1016/j.isprsjprs.2024.12.014
- Mulverhill, C., Coops, N. C., & Achim, A. (2023). Continuous monitoring and
  sub-annual change detection in high-latitude forests using Harmonized
  Landsat Sentinel-2 data. *ISPRS Journal of Photogrammetry and Remote
  Sensing*, 197, 309-323.
- Zhao, K., Wulder, M. A., Hu, T., Bright, R., Wu, Q., Qin, H., Li, Y., Toman,
  E., Mallick, B., Zhang, X., & Brown, M. (2019). Detecting change-point,
  trend, and seasonality in satellite time series data to track abrupt changes
  and nonlinear dynamics: A Bayesian ensemble algorithm. *Remote Sensing of
  Environment*, 232, 111181.
  https://doi.org/10.1016/j.rse.2019.04.034

## Licence

Apache-2.0 for this package. `Rbeast` is an optional external GPL-2/GPL-3
dependency and is not redistributed here.
