# VeraLux Suite Upstream Notes

`veralux` is an AfterNight port/adaptation of the original VeraLux Siril script
suite by Riccardo Paterniti.

## Captured Baseline

- Upstream repository: https://gitlab.com/free-astro/siril-scripts.git
- Upstream directory: `VeraLux/`
- Captured checkout: `4ce0af52926e071caef55f4d17ac17ae8d8b4aac`
- Latest captured VeraLux directory commit: `730814465d3c742a3e99a192083fc9d7b1bd0e59`

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
- Preview-specific zoom, compare, and live auto-stretched preview behavior are
  deferred to a later native-preview polish slice.
