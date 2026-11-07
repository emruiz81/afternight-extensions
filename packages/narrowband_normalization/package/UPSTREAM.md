# Narrowband Normalization Upstream Notes

`narrowband_normalization` is an AfterNight port of Yannick Dutertre's
NarrowbandNormalization script for Siril. The script implements Bill Blanshan
and Mike Cranfield's NarrowbandNormalization PixInsight mathematics
(HOSNormalization, https://cosmicphotons.com/scripts/) as a clean-room
implementation, with Bill Blanshan's permission.

## Captured Baseline

- Upstream repository: https://gitlab.com/free-astro/siril-scripts.git
- Captured checkout: `c7a185babc74141bfb082059166ede79e4b80ee2`
- Original file: `processing/NarrowbandNormalization.py`
- Latest file-specific commit: `be8cdaa9f65730fb27ac4f5b913e31a501dda131`
- Original file SHA-256 at the captured checkout:
  `87bd4e4608dfda9a0d7bce0597e387ba0b1a7f83eaf4fdb32e7589da3863cb72`
- Original version constant: `1.0.5`

Verify the baseline, or see what changed in a newer checkout, with:

```bash
python3 tools/check_upstream.py \
  --package-dir packages/narrowband_normalization/package \
  --upstream-checkout /path/to/siril-scripts [--ref HEAD]
```

## Port Structure

- `narrowband_normalization_core.py` holds the upstream "CORE MATH ENGINE" and
  "PALETTE HANDLING" sections unchanged, plus `normalize_input`.
- `narrowband_normalization_ui.py` declares the native process-window
  parameters, with the upstream dialog's ranges and defaults.
- `narrowband_normalization_extension.py` is the entry point: it reads the
  AfterNight image, runs the core and writes the result.

## Intentional Divergences

- sirilpy image access, undo and logging are replaced by AfterNight SDK image
  handles, metadata and logging.
- The PyQt6 dialog and its 720-pixel preview proxy are replaced by native
  parameters and RT preview. The preview processes the whole image, or the
  chosen preview sub-area, at full resolution, so its statistics are the ones
  Apply uses.
- Integer images are divided by their sample type's maximum. Upstream divides
  any image whose maximum passes 1.5 by 65535, which leaves 8-bit and 32-bit
  integer images outside [0, 1]. Floating-point images keep the upstream rule.
- The result is written back in the source's sample type.
- Every Lightness choice stays available for every palette. The upstream dialog
  hides SII for HOO; the upstream engine, kept here, uses OIII for it.
