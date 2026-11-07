# Continuum Subtraction Publication Readiness

Status: source-staged as `continuum_subtraction` version `0.1.0`; not
published.

## Completed Gates

- Package layout: manifest with two processes, entry point, GPL-3.0 `LICENSE`
  under a GPL-3.0-only declaration, `THIRD_PARTY_NOTICES.md`, `UPSTREAM.md` and
  `UPSTREAM.json`.
- Provenance: `tools/check_upstream.py` verifies the captured Siril scripts
  baseline, reading the upstream lowercase `version` constant.
- Automated checks: package tests cover the estimate (recovery of a known
  factor, its documented bias when emission follows the continuum, the fit
  fallback), both adapters (painted region, manual c, the estimate cache,
  sample types, channel layouts, refusals) and both schemas. The parity tests
  hold the AAD, the coarse scan and the estimated c identical to the upstream
  script's.

## Open Gates

- Representative real-image visual QA in AfterNight: Ha and continuum stacks of
  a galaxy and of an emission nebula, and a blend into their RGB image.
- Host check: both process windows open, the continuum and line view pickers
  list matching views, the estimation region can be painted and is used, RT
  preview works, and Apply output matches the preview.
- Release signoff, then a `repository.json` release entry with
  `asset_base_url`, removal of `"publish": false`, and the package id in the
  publish workflow's dropdown.

## Validation

```bash
python3 -m unittest discover -s packages/continuum_subtraction/tests
python3 tools/check_upstream.py \
  --package-dir packages/continuum_subtraction/package \
  --upstream-checkout ../siril-scripts
python3 tools/build_package.py packages/continuum_subtraction/package --output-dir dist
```
