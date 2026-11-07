# HDR Multiscale Publication Readiness

Status: source-staged as `hdr_multiscale` version `0.1.0`; not published.

## Completed Gates

- Package layout: manifest, entry point, GPL-3.0-or-later `LICENSE`,
  `THIRD_PARTY_NOTICES.md`, `UPSTREAM.md` and `UPSTREAM.json`.
- Provenance: `tools/check_upstream.py` verifies the captured Siril scripts
  baseline.
- Automated checks: package tests cover the core (RGB, mono, mask output,
  repeatable output at ten scales on a small area), the adapter (sample types,
  channel layouts, cancellation, metadata) and the parameter schema. The parity
  tests hold the core and the applied result bit-identical to the upstream
  script's wherever SciPy's convolution is stable.
- Speed: about 2 seconds for a 6-megapixel RGB image at 5 to 10 scales.

## Open Gates

- Representative real-image visual QA in AfterNight on stretched images with
  bright cores (M42, galaxy nuclei), mono and RGB.
- Host check: the process window opens, RT preview and the preview sub-area
  work, Show Luminance Mask renders, and Apply output matches the preview.
- Release signoff, then a `repository.json` release entry with
  `asset_base_url`, removal of `"publish": false`, and the package id in the
  publish workflow's dropdown.

## Validation

```bash
python3 -m unittest discover -s packages/hdr_multiscale/tests
python3 tools/check_upstream.py \
  --package-dir packages/hdr_multiscale/package \
  --upstream-checkout ../siril-scripts
python3 tools/build_package.py packages/hdr_multiscale/package --output-dir dist
```
