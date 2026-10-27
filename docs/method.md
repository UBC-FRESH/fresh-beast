# Method and provenance

## Reference workflow

The implementation follows the published HLS/BEAST NSR workflow in Brown et
al. (2025):

1. HLS L30 and S30 surface reflectance at 30 m.
2. NBR = `(NIR - SWIR2) / (NIR + SWIR2)`.
   - L30: `B05` = NIR, `B07` = SWIR2.
   - S30: `B8A` = NIR, `B12` = SWIR2.
3. Mask HLS `Fmask` bits 0-4 (cloud, adjacent cloud, cloud shadow, snow/ice,
   water) and the `255` fill value.
4. Average valid NBR values into regular 16-day composites.
5. Run BEAST (`Rbeast`) with harmonic seasonality and an annual period.
6. Convert the negative changepoint probability (`neg_cpOccPr`) into an annual
   probability surface.

The Brown et al. paper does not publish the exact `Rbeast` argument list, the
MCMC seed, or a BEAST-to-severity mapping. `fresh-beast` therefore keeps the
reference defaults and records the installed Rbeast version. It does not
invent a severity class.

## BEAST time axis

BEAST requires a regular time axis. Calendar dates are not exactly regular in
decimal years because of leap years, so the package uses:

- first composite date converted to decimal years;
- every subsequent step exactly `16 / 365.25` years;
- `season = "harmonic"`;
- `period = 1.0` year;
- `start = first decimal year`;
- Rbeast defaults for MCMC and priors.

The original calendar dates remain in the composite stack and are used for
annual grouping. This distinction matters around 31 December.

## Detection rule

`neg_cpOccPr` is the BEAST probability of a negative changepoint at each
composite. The package computes the maximum value in each calendar year and
emits an event when:

- the annual maximum is at least `--threshold` (default `0.5`, from
  Mulverhill et al. 2023), and
- the pixel has at least `--min-valid` valid composites (default `60`; a
  stability guard, not a paper coefficient).

Consecutive above-threshold years are grouped into one episode and the peak
year is reported. With `--min-consecutive-years 2`, single-year exceedances are
suppressed.

Pixel detections are rasterized to block ids from a block layer with a
`block_id` column. One `femic.disturbance.v1` event is emitted per block and
year. `event_type` is `partial_mortality`; no agent is attributed.

## Deliberate gaps

| Gap | Handling |
|---|---|
| Landsat 2000-2015 spin-up | Not included in the current HLS-only pilot |
| NTEMS VLCE forest mask | Not applied; caller must mask non-forest |
| AOS agent/severity validation | Not claimed; separate join required |
| BEAST-to-severity mapping | `severity_class = "unknown"` |
| MCMC/pseudo-prior choices not in paper | Rbeast defaults, recorded |
| S30 availability before 2015 | 2013-2014 use L30 only |

## Exact provenance

Each run writes:

- `hls_granules.json`: every HLS granule id, collection, acquisition time, and
  size;
- `hls_composites.npz`: NBR, observation counts, dates, CRS, transform, AOI;
- `result.json`: Rbeast version, method, thresholds, grid summary, caveats,
  and events;
- `annual_probability.csv` and `beast_pixels.csv`: per-pixel diagnostics.

The package never writes Earthdata credentials. It reads the standard
`~/.netrc` entry for `urs.earthdata.nasa.gov`.
