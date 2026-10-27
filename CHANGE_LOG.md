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
- TSA 23 block 1356 / 2024 AOS cluster: 1,174 HLS granules, 297 composites,
  1,444/1,444 pixels processed, 60 events across 19/20 blocks inside a 2024
  IDW/Severe polygon. 18 blocks have a 2023 event; one block has no event.
- Consumer tests against FEMIC's contract validator and WS4's event reader.
- TSA 23 2019 ID6 case-control validation: 31 positive / 47 control blocks,
  3,876 pixels, 37 events. At 2018-2020 sensitivity is 25.8%, specificity
  66.0%, precision 33.3%. The detector is not operational at 0.5.
