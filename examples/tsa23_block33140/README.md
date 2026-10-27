# TSA 23 block 33140 pilot

This directory is populated by:

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
layer. The AOI is a 1 km window around block 33140 in TSA 23.

The pilot is **not** an AOS validation. It exercises the HLS -> NBR -> BEAST ->
`femic.disturbance.v1` path on public data. See the generated `result.json`
for the exact granule count, Rbeast version, probabilities, and caveats.
