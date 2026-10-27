# Change log

## 0.1.0a1

- Initial public package.
- HLS L30/S30 search, windowed reads, Fmask masking, NBR, and 16-day mean
  composites.
- Reference Rbeast bridge with harmonic annual seasonality and provenance for
  the installed Rbeast version.
- Negative-changepoint annual probability and block-level
  `femic.disturbance.v1` events.
- `fresh.beast.v1` result document with explicit method and caveats.
- TSA 23 block 33140 negative-control pilot: 636 HLS granules, 183 composites,
  840/840 pixels processed, 0 events at the 0.5 threshold (max in-block
  probability 0.348).
- TSA 23 block 1356 / 2025 AOS pilot: 1,174 HLS granules, 297 composites,
  1,444/1,444 pixels processed, two events (2018 and 2023) inside a 2025 AOS
  IDW/Severe polygon; the 2023 event is two years before the AOS capture.
- Consumer tests against FEMIC's contract validator and WS4's event reader.
