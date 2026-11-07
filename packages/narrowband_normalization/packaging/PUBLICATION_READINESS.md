# Narrowband Normalization Publication Readiness

Status: source-staged as `narrowband_normalization` version `0.1.0`; not
published.

## Completed Gates

- Package layout: manifest, entry point, GPL-3.0-or-later `LICENSE`,
  `THIRD_PARTY_NOTICES.md`, `UPSTREAM.md` and `UPSTREAM.json`.
- Provenance: `tools/check_upstream.py` verifies the captured Siril scripts
  baseline.
- Automated checks: package tests cover the engine, the adapter (sample types,
  channel layouts, cancellation, metadata) and the parameter schema. The parity
  tests hold the engine's output bit-identical to the upstream script's for
  every palette, every lightness source and a spread of control values.

## Open Gates

- Representative real-image visual QA in AfterNight: SHO and HOO data from mono
  narrowband stacks and from OSC dual-band stacks.
- Host check: the process window opens, the palette greys out the right
  controls, RT preview and the preview sub-area work, and Apply output matches
  the preview.
- Release signoff, then a `repository.json` release entry with
  `asset_base_url`, removal of `"publish": false`, and the package id in the
  publish workflow's dropdown.

## Validation

```bash
python3 -m unittest discover -s packages/narrowband_normalization/tests
python3 tools/check_upstream.py \
  --package-dir packages/narrowband_normalization/package \
  --upstream-checkout ../siril-scripts
python3 tools/build_package.py packages/narrowband_normalization/package --output-dir dist
```
