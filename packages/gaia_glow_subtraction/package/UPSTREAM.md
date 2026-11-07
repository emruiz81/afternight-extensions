# Gaia Glow Subtraction Upstream Notes

`gaia_glow_subtraction` is an AfterNight port of GaiaGlowSubtraction for Siril
by Adrian Knagg-Baugh, an independent reimplementation of PixInsight's
PhotometricGlowSubtraction from its public documentation.

## Captured Baseline

- Upstream repository: https://gitlab.com/free-astro/siril-scripts.git
- Captured checkout: `c7a185babc74141bfb082059166ede79e4b80ee2`
- Original file: `processing/GaiaGlowSubtraction.py`
- Latest file-specific commit: `47fed0e695c0d684827f839dc3d317e40d3f05ef`
- Original file SHA-256 at the captured checkout:
  `c9985ad21c6924f6d4772163219ef8ae9bb4e0fbf3c062b41ff65ee204990543`
- Original version constant: `1.2.6`

Verify the baseline, or see what changed in a newer checkout, with:

```bash
python3 tools/check_upstream.py \
  --package-dir packages/gaia_glow_subtraction/package \
  --upstream-checkout /path/to/siril-scripts [--ref HEAD]
```

## Port Structure

- `gaia_glow_subtraction_core.py` is the upstream script's lines 1-7400, its
  sections 0 to 13 (constants, parameters, numerical helpers, catalogue access,
  synthetic photometry, geometry, the joint fit, rendering, the extended PSF,
  star selection, glow rendering, misuse checks and the `GlowSubtractor`
  orchestration), unchanged apart from the sirilpy import block (upstream lines
  122-127). `test_gaia_glow_subtraction_vendor.py` holds it to the upstream
  text. To refresh it, regenerate it from the new upstream file and update this
  baseline; do not edit it by hand.
- `gaia_glow_subtraction_io.py` replaces section 14, `SirilIO`, with
  `AfterNightIO` over an AfterNight image handle.
- `gaia_glow_subtraction_ui.py` and `gaia_glow_subtraction_extension.py`
  replace sections 15 and 16 (the PyQt6 GUI and the command line) with a native
  Apply-only process window and its settings, and do what the upstream
  `finish_run` does after a run.

## Pixel Conventions

The core works on arrays in FITS storage order, with astropy's 0-based pixel
centres. AfterNight keeps a FITS image's rows in storage order (`ROWORDER`
only sets how they are displayed) and writes WCS cards against those rows, so
no flip is needed. AfterNight's star finder reports positions with the first
pixel's centre at one half, so a detection's core position is its x and y minus
one half. Upstream needs a row flip and the same half-pixel shift for Siril's
display-frame `findstar` positions.

## Intentional Divergences

- The FITS header comes from the image's AfterNight header cards, each typed
  by parsing its raw 80-character record; keywords, HISTORY and DATE-OBS come
  from the same cards.
- Stars are detected with AfterNight's star finder instead of Siril's
  `findstar`, on each channel of a colour image.
- The catalogue cache, the bright-star table and the last-output record live in
  a folder chosen in the package settings, by default a per-user cache folder,
  instead of Siril's user data folder. Choosing Siril's user data folder shares
  its cache. Local Siril catalogues can be named in the settings.
- Siril's SPCC preferences have no AfterNight counterpart, so the core uses its
  top-hat channel responses; it still fits a zero point and colour term on the
  image's own stars.
- Without a dialog, soft refusals need Proceed Despite Warnings and an
  oversized download needs a higher download limit, as the upstream command
  line's `-force` and `-maxdownload` do.
- PSF from a selection is left out: it needs Siril's rectangle selection.
  Measure the PSF or load one saved earlier.
- Integer images are written back in their own sample type, the glow model
  opens as a new image instead of a file next to the input, and the output's
  fingerprint is recorded in the cache folder so a second subtraction is
  refused.
- The linear-WCS warning is worded for AfterNight instead of Siril, by
  replacing the core's `LINEAR_WCS_MSG` constant at import.
