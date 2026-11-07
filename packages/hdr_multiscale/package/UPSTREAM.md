# HDR Multiscale Upstream Notes

`hdr_multiscale` is an AfterNight port of HDR Multiscale for Siril, written by
Franklin Marek for Seti Astro Suite and adapted for Siril by Cyril Richard.

## Captured Baseline

- Upstream repository: https://gitlab.com/free-astro/siril-scripts.git
- Captured checkout: `c7a185babc74141bfb082059166ede79e4b80ee2`
- Original file: `processing/HDR_multiscale.py`
- Latest file-specific commit: `adec9065c0c095af0cf7d245f76adcfbc38a62d3`
- Original file SHA-256 at the captured checkout:
  `a8b09d84b6b9132f8afff5eb41d91ae44dc2fade04580c4dff5b5666a21d168a`
- Original version constant: `1.0.2`

Verify the baseline, or see what changed in a newer checkout, with:

```bash
python3 tools/check_upstream.py \
  --package-dir packages/hdr_multiscale/package \
  --upstream-checkout /path/to/siril-scripts [--ref HEAD]
```

## Port Structure

- `hdr_multiscale_core.py` holds the upstream "Core Math Functions" section
  unchanged apart from `_conv_sep_reflect` (below). `apply_hdr_multiscale` does
  what the upstream dialog does around it: mono images run as three equal
  channels and come back as their mean, and the transformed image is blended
  with the source through the luminance mask.
- `hdr_multiscale_ui.py` declares the native process-window parameters, with
  the upstream dialog's ranges and defaults.
- `hdr_multiscale_extension.py` is the entry point: it reads the AfterNight
  image, runs the core and writes the result.

## Intentional Divergences

- sirilpy image access, undo and logging are replaced by AfterNight SDK image
  handles, metadata and logging.
- The PyQt6 dialog, its worker thread and its Preview button are replaced by
  native parameters and RT preview over the whole image or the chosen preview
  sub-area. The core's midtones alignment uses whole-image medians, so the
  preview never runs on a reduced copy.
- `_conv_sep_reflect` computes the reflect-padded a-trous convolution from the
  kernel's non-zero taps in NumPy instead of calling
  `scipy.ndimage.convolve`. When a scale's dilated kernel is much longer than
  the image, as at high scale counts on a small preview sub-area, SciPy's result
  changes from run to run and can be NaN. The NumPy form adds the same taps in
  SciPy's order in float64, so it is bit-identical to SciPy wherever SciPy is
  stable; the package therefore no longer needs SciPy.
- Integer images are divided by their sample type's maximum, as sirilpy's
  float conversion does, and the result is written back in the source's sample
  type.
- A Show Luminance Mask option, absent upstream, outputs the blending mask to
  help set Mask Gamma.
