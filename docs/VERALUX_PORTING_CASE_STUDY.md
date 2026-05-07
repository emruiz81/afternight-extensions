# VeraLux Porting Case Study

This document captures the first full third-party suite port to the AfterNight
extension SDK: Riccardo Paterniti's VeraLux Siril scripts.

> **Audience:** maintainers planning a port of a multi-process upstream suite.
> Use this as a pattern reference, not as the normative package schema.

## Why This Case Study Matters

The VeraLux port is the repository's reference example for a package that needs:

- explicit upstream provenance and derived-work attribution
- a multi-process package layout
- dependency isolation across several related tools
- native AfterNight parameter schemas instead of upstream UI code
- layered automated quality checks before publication

## Source And Scope

VeraLux was ported from the Siril scripts repository at upstream commit
`4ce0af52926e071caef55f4d17ac17ae8d8b4aac`. The original source files live in
`VeraLux/` and carry `SPDX-License-Identifier: GPL-3.0-or-later` headers, so the
AfterNight ports preserve GPL-3.0-or-later terms for derived code. The suite
package keeps machine-readable provenance in
`packages/veralux/package/UPSTREAM.json` and human-readable notes in
`packages/veralux/package/UPSTREAM.md`.

The package is suite-scoped. One `veralux` package registers eight processing
processes:

- Revela
- Alchemy
- HyperMetric Stretch
- Curves
- Nox
- Silentium
- Vectra
- StarComposer

The original `VeraLux_Starting_Point.py` script is documentation, not a process,
and is adapted as `packages/veralux/package/STARTING_POINT.md`.

## Port Shape

Each process is split into the same three layers:

- `*_core.py`: VeraLux-derived algorithm code with minimal AfterNight coupling
- `*_adapter.py`: AfterNight SDK image handles, metadata, logging, progress,
  and process execution
- `*_ui.py`: native `get_params()` schemas rendered by the AfterNight process
  window

Shared SDK glue lives in `packages/veralux/package/veralux_sdk.py`. That helper
owns repeated image-handle conversion, result metadata, logging wrappers,
settings migration, preview downsampling and autostretch, optional mask
extraction, and star-mask construction from
`afternight.registration.find_stars()`.

This structure keeps upstream algorithm refreshes reviewable: compare the new
upstream script against the local `*_core.py`, then update the adapter or UI
layer only when AfterNight integration behavior changes.

## Siril To AfterNight Mapping

The port replaces Siril process-host services with AfterNight SDK concepts:

- Siril image access becomes `ImageHandle.to_numpy()` and
  `ImageHandle.from_numpy()`.
- Siril logging becomes `afternight.log_info()` and
  `afternight.log_warning()` through the VeraLux shared SDK helper.
- Siril save or load behavior maps to `afternight.io.load()` and
  `afternight.io.save()` when a process needs explicit file orchestration.
- Siril star detection maps to `afternight.registration.find_stars()`.
- PyQt6 process dialogs become native AfterNight parameter schemas.

The first release intentionally avoids launch-time custom PySide6 widgets. That
keeps the package fast to cache while still allowing richer host-native schema
controls such as Curves' histogram-backed curve editor.

## Dependency Choices

The package uses one private dependency environment and one lockfile for the
suite. It keeps `numpy` as the common numerical dependency, includes
`opencv-python-headless` for the supported Revela path, and includes SciPy plus
PyWavelets for Silentium's upstream SWT or db2 denoise path. The port
deliberately avoids adding Astropy and PyQt6 to the baseline lockfile:

- Curves uses package-local Akima-style interpolation.
- Nox uses package-local membrane-style background modeling.
- Silentium uses PyWavelets and SciPy when installed and keeps a NumPy fallback
  for minimal test environments.
- StarComposer uses package-local blur and morphology helpers.

Those choices reduce install size and remove dependencies that were only needed
for Siril-specific UI or file workflows in the first native slice.

## Quality Strategy

The package uses layered validation rather than relying on visual inspection
alone:

- Core unit tests cover each process on deterministic synthetic fixtures.
- Regression-metric tests pin compact output summaries for all eight cores.
- Upstream-quality tests compare directly comparable cores against a captured
  local Siril source checkout with Siril or PyQt stubs.
- Archive smoke tests build and decompress the real package asset.
- Host integration tests in the main AfterNight repo cover discovery,
  per-process schema caching, runtime host execution, and large NumPy image
  roundtrips.

Known first-pass differences are recorded in
`packages/veralux/package/QUALITY_VALIDATION.md`. The final publication blocker
is representative real-image visual QA and release signoff, tracked in
`packages/veralux/packaging/PUBLICATION_READINESS.md`.

## Deferred Parity

Several upstream UI workflows are intentionally deferred from the initial
AfterNight-native release:

- Vectra vector-scope HUD
- Nox manual mask painting and BVI preview overlays
- Silentium loupe preview and PSF-list masking

The core and helper layers leave a path for those future slices. Nox and
Silentium can use `veralux_sdk.star_mask_from_find_stars()` when PSF-list parity
is promoted. StarComposer now uses the active target as the starless base and a
second open view as the stars or starmask input through the AfterNight view
snapshot API.

## Upstream Refresh Workflow

Use `tools/check_veralux_upstream.py` against a local Siril scripts checkout
before updating the port. A clean refresh should land in two reviewable steps:

1. Update the captured upstream provenance and hashes.
2. Update local `*_core.py`, adapter or UI code, tests, and quality notes.

This keeps upstream behavior changes separate from AfterNight integration
choices, which is especially important for GPL-derived code and future release
audits.

## Reusable Lessons

Future ports should reuse these patterns:

- preserve upstream provenance in both machine-readable and human-readable files
- keep a clear separation between upstream-derived core logic and AfterNight
  integration glue
- avoid carrying upstream UI dependencies when native AfterNight controls can
  replace them
- keep deferred parity items documented rather than hidden in code comments
- validate with layered tests so visual QA is a release gate, not the only gate

## Related Docs

- [README.md](README.md)
- [PACKAGE_FORMAT.md](PACKAGE_FORMAT.md)
- [LICENSING.md](LICENSING.md)
- [RELEASE_PROCESS.md](RELEASE_PROCESS.md)
