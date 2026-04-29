# VeraLux Revela Upstream Notes

`veralux_revela` is an AfterNight port/adaptation of the original VeraLux
Revela Siril script by Riccardo Paterniti.

## Captured Baseline

- Upstream repository: https://gitlab.com/free-astro/siril-scripts.git
- Upstream directory: `VeraLux/`
- Captured checkout: `4ce0af52926e071caef55f4d17ac17ae8d8b4aac`
- Latest captured VeraLux directory commit: `730814465d3c742a3e99a192083fc9d7b1bd0e59`
- Original file: `VeraLux/VeraLux_Revela.py`
- Latest file-specific commit in the local checkout: `15940a9e12b1700ae4c3e8aee8f00c7303e19b7f`
- Original file SHA-256 at captured checkout: `3c094fbda2d9b6810af15604c5c7110a3f1c80dfe4d61acc32e3d68349298cd4`
- Original VeraLux version constant: `1.0.2`

## Port Structure

- `veralux_revela_core.py` keeps the derived image-processing algorithm with
  minimal AfterNight coupling.
- `veralux_revela_adapter.py` maps AfterNight SDK image handles, progress, and
  metadata to the core.
- `veralux_revela_ui.py` declares native process-window parameters and visible
  attribution.

## Intentional Divergences

- `sirilpy` image loading, image locking, undo, and logging were replaced by the
  AfterNight extension SDK.
- The PyQt6 window was replaced with AfterNight native process-window parameter
  definitions.
- OpenCV is still the preferred runtime for Lab conversion and fast filters, but
  the port keeps a small NumPy fallback for package tests and diagnostics when
  OpenCV is unavailable.
- Preview-specific zoom, compare, and background-worker UI behavior are deferred
  to a later native-preview polish slice.
