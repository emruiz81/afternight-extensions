# Continuum Subtraction Upstream Notes

`continuum_subtraction` is an AfterNight port of Narrowband Continuum
Subtraction for Siril by Adrian Knagg-Baugh and Dave Lindner.

## Captured Baseline

- Upstream repository: https://gitlab.com/free-astro/siril-scripts.git
- Captured checkout: `c7a185babc74141bfb082059166ede79e4b80ee2`
- Original file: `processing/ContinuumSubtraction.py`
- Latest file-specific commit: `20f08562585289fc9235f702093f10cb90f0ba2d`
- Original file SHA-256 at the captured checkout:
  `c449e7f9de75e544e216a5fb7269aea4b85d1af8c64dfff5ea9ce7cc6c40fe75`
- Original version constant: `v3.0.7`, in the lowercase `version` assignment
  (`"version_constant": "version"` in `UPSTREAM.json`)

Verify the baseline, or see what changed in a newer checkout, with:

```bash
python3 tools/check_upstream.py \
  --package-dir packages/continuum_subtraction/package \
  --upstream-checkout /path/to/siril-scripts [--ref HEAD]
```

## Port Structure

- `continuum_subtraction_core.py` holds the upstream estimate (`aad`,
  `find_min`, `compute_c` and its smooth-V model) and the dialog's Generate and
  Blend arithmetic as `subtract_continuum` and `blend_into_rgb`.
- `continuum_subtraction_ui.py` declares the native process-window parameters
  of both processes.
- `continuum_subtraction_extension.py` is the entry point with the two process
  classes, `ContinuumSubtractionExtension` and `ContinuumBlendExtension`.

## Intentional Divergences

- sirilpy image access, selection statistics, progress and logging, and the
  astropy FITS files the dialog reads and writes, are replaced by AfterNight SDK
  image handles, open views, metadata and logging.
- The dialog's Estimate, Generate and Blend buttons become two processes:
  Continuum Subtraction estimates c, or takes it from the slider, and subtracts
  the continuum from the emission image; Continuum Blend adds a
  continuum-subtracted line into an RGB image.
- The estimation region is a painted manual mask instead of a Siril selection
  rectangle. Without one the whole image is used, as upstream does, with the
  same warning in the log.
- While Estimate c Automatically is on, c is estimated on every preview and
  Apply and written to the log, because the SDK has no way for a run to move
  the c slider. The estimate is cached until the images or the region change.
- When the smooth-V fit fails, or its starting point is infeasible because the
  AAD minimum sits below zero, c falls back to the fine scan's best factor
  clipped to [0, 1]; upstream ends the estimate with an error.
- The continuum comes from an open mono view, and the blend writes into an open
  RGB view, instead of separate R, G, B and line files. Images are compared in
  [0, 1], with integer samples divided by their type's maximum; integer results
  are clipped to their range, float results are written unclipped as upstream
  writes them.
- The dialog's per-line channel choice is a Channels preset (Ha into red, SII
  into green, OIII into blue, as upstream) or custom weights.
- The matplotlib plot of the fit is dropped.
