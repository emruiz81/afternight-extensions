# VeraLux Suite Upstream Notes

`veralux` is an AfterNight port/adaptation of the original VeraLux Siril script
suite by Riccardo Paterniti.

## Captured Baseline

- Upstream repository: https://gitlab.com/free-astro/siril-scripts.git
- Upstream directory: `VeraLux/`
- Captured checkout: `4ce0af52926e071caef55f4d17ac17ae8d8b4aac`
- Latest captured VeraLux directory commit: `730814465d3c742a3e99a192083fc9d7b1bd0e59`

## Refresh Workflow

Use the repository-local provenance checker to verify this package against a
local `siril-scripts` checkout:

```bash
python3 tools/check_veralux_upstream.py --upstream-checkout /path/to/siril-scripts
```

The command compares every `sources[]` entry in `UPSTREAM.json` against the
selected git ref, including source SHA-256, file-specific last commit, and the
VeraLux `VERSION` constant. Passing the default check confirms the captured
baseline is internally consistent. Passing `--ref HEAD` against a refreshed
upstream checkout shows which VeraLux sources changed and which local port
modules need review before updating the baseline.

## Included Sources

### Revela

- Original file: `VeraLux/VeraLux_Revela.py`
- Latest file-specific commit in the local checkout: `15940a9e12b1700ae4c3e8aee8f00c7303e19b7f`
- Original file SHA-256 at captured checkout: `3c094fbda2d9b6810af15604c5c7110a3f1c80dfe4d61acc32e3d68349298cd4`
- Original VeraLux version constant: `1.0.2`
- Port modules: `veralux_revela_core.py`, `veralux_revela_adapter.py`,
  `veralux_revela_ui.py`

### Alchemy

- Original file: `VeraLux/VeraLux_Alchemy.py`
- Latest file-specific commit in the local checkout: `cd4c8a6600455985d6764bbd61831728d11ac36a`
- Original file SHA-256 at captured checkout: `0b627b4bd5ae3836c7d823cf5a10017e64ba594995f605c73ebb420347b0be3e`
- Original VeraLux version constant: `1.0.3`
- Port modules: `veralux_alchemy_core.py`, `veralux_alchemy_adapter.py`,
  `veralux_alchemy_ui.py`

### HyperMetric Stretch

- Original file: `VeraLux/VeraLux_HyperMetric_Stretch.py`
- Latest file-specific commit in the local checkout: `730814465d3c742a3e99a192083fc9d7b1bd0e59`
- Original file SHA-256 at captured checkout: `5b9704c0dac81dac71fb0be4b5c0efae7276cf68a7285f777f341b62fb90c571`
- Original VeraLux version constant: `1.5.2`
- Port modules: `veralux_hypermetric_stretch_core.py`,
  `veralux_hypermetric_stretch_adapter.py`,
  `veralux_hypermetric_stretch_ui.py`

### Curves

- Original file: `VeraLux/VeraLux_Curves.py`
- Latest file-specific commit in the local checkout: `2f5687449a88bf0681430a3f577a044634ba5647`
- Original file SHA-256 at captured checkout: `bd5f2b41e7f19ac8276438fdc20742c6990cedb3e1d9eef66d194113d16ce00b`
- Original VeraLux version constant: `1.0.1`
- Port modules: `veralux_curves_core.py`, `veralux_curves_adapter.py`,
  `veralux_curves_ui.py`

### Nox

- Original file: `VeraLux/VeraLux_Nox.py`
- Latest file-specific commit in the local checkout: `a9fb2c7f505c488f5cfef5b7fa5022097551e06e`
- Original file SHA-256 at captured checkout: `89ff9da4fea181b1d3742cd325748ee7decf78ebe36061d7f0f6e93a385f52d8`
- Original VeraLux version constant: `1.0.1`
- Port modules: `veralux_nox_core.py`, `veralux_nox_adapter.py`,
  `veralux_nox_ui.py`

### Silentium

- Original file: `VeraLux/VeraLux_Silentium.py`
- Latest file-specific commit in the local checkout: `f70698e25f7c00d32593ba7ad3f1eb68ffe6a218`
- Original file SHA-256 at captured checkout: `62e9db5e1f470d38d8e635da9d1f892ee59ab6b6477e471b69d2725de5d655f8`
- Original VeraLux version constant: `1.0.3`
- Port modules: `veralux_silentium_core.py`,
  `veralux_silentium_adapter.py`, `veralux_silentium_ui.py`

### Vectra

- Original file: `VeraLux/VeraLux_Vectra.py`
- Latest file-specific commit in the local checkout: `c418d44a734d51a4cc4d7a51b0bb798d98582c2b`
- Original file SHA-256 at captured checkout: `eca04c83e51815cfd69894c5526ecea8ec0a0f3345a6a77c63f787306cfed9a9`
- Original VeraLux version constant: `1.0.3`
- Port modules: `veralux_vectra_core.py`, `veralux_vectra_adapter.py`,
  `veralux_vectra_ui.py`

### StarComposer

- Original file: `VeraLux/VeraLux_StarComposer.py`
- Latest file-specific commit in the local checkout: `85fc3c17f9df8920dac7b0c867609a25e3415a1c`
- Original file SHA-256 at captured checkout: `280230908a7547d82c86c386f0d820b037147c46fe6f51148359ecd804008a23`
- Original VeraLux version constant: `2.1.0`
- Port modules: `veralux_starcomposer_core.py`,
  `veralux_starcomposer_adapter.py`, `veralux_starcomposer_ui.py`

### Starting Point

- Original file: `VeraLux/VeraLux_Starting_Point.py`
- Latest file-specific commit in the local checkout: `667be9dcd9a6bebeab6805168d30e91485566d94`
- Original file SHA-256 at captured checkout: `1342e6fdcb5c33dcee541e372d959c460de6166b253a7fbba73fd9a11f76a3fb`
- Original VeraLux version constant: `1.0.0`
- Port module: `STARTING_POINT.md`
- Notes: Starting Point is a workflow guide, not a processing engine, so the
  AfterNight package adapts it into documentation rather than registering a
  process.

## Port Structure

- `veralux_extension.py` is the suite entry point and exports all process
  classes registered by `extension.json`.
- `*_core.py` modules keep derived image-processing algorithms with minimal
  AfterNight coupling.
- `*_adapter.py` modules map AfterNight SDK image handles, progress, and
  metadata to each core.
- `*_ui.py` modules declare native process-window parameters and visible
  attribution.

## Intentional Divergences

- `sirilpy` image loading, image locking, undo, save/load, and logging were
  replaced by the AfterNight extension SDK.
- PyQt6 windows were replaced with AfterNight native process-window parameter
  definitions.
- Revela keeps OpenCV as the preferred runtime for Lab conversion and fast
  filters, with a small NumPy fallback for package tests and diagnostics when
  OpenCV is unavailable.
- Alchemy is array-based in this port, so it does not require astropy for the
  first native process implementation.
- HyperMetric Stretch keeps the core tone-mapping path NumPy-only and preserves
  the source image layout when returning through the AfterNight SDK boundary.
- Curves uses a package-local NumPy Akima-style Hermite interpolator instead of
  adding SciPy only for this process. The first native UI exposes a parametric
  curve operation; arbitrary point editing, histograms, and applied-stage stack
  parity are deferred to a later native UI slice.
- Nox uses a package-local NumPy membrane-smoothing background estimator instead
  of requiring SciPy sparse solvers for this first native slice. Manual mask
  painting, BVI dialog parity, and preview overlays are deferred to later host
  integration.
- Silentium uses a package-local NumPy multiscale detail-thresholding path
  instead of requiring PyWavelets and SciPy for the first native slice. PSF-list
  masking and loupe UI parity are deferred to later host integration.
- Vectra uses a package-local NumPy reflect-convolution helper instead of
  adding SciPy for its small blur/filter needs.
- StarComposer is exposed first as active star-mask shaping because the native
  process UI does not yet provide multi-input file selection. Starless
  compositing is available in the core for a later host UI slice.
- Starting Point is adapted from a PyQt6 interactive guide into
  `STARTING_POINT.md`, preserving the workflow order and attribution while
  avoiding a non-processing extension entry.
- Preview-specific zoom, compare, and live auto-stretched preview behavior are
  deferred to a later native-preview polish slice.
