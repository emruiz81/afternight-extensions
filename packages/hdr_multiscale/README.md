# HDR Multiscale

HDR Multiscale is an AfterNight port of HDR Multiscale for Siril, written by
Franklin Marek for Seti Astro Suite and adapted for Siril by Cyril Richard.

It compresses the dynamic range of a stretched, non-linear mono or RGB image,
for bright cores such as M42 or a galaxy's nucleus:

- decomposes Lab lightness with an a-trous B3-spline wavelet
- boosts the detail layers through a luminance mask, less at coarser scales
- realigns the midtones and applies a dimming curve
- blends the result in through the luminance mask, so the background keeps its
  values

The package registers one process, **HDR Multiscale**, with RT preview and a
Show Luminance Mask option for setting Mask Gamma. It needs no Python
dependencies beyond NumPy from AfterNight's shared `scientific_core` profile.

This is a full hosted package (`sdk_backend = runtime`) under
GPL-3.0-or-later. It is source-staged (`"publish": false`): it validates and is
tested here but stays out of the repository index until its release gates in
`packaging/PUBLICATION_READINESS.md` are met.

## Provenance

`package/UPSTREAM.md` and `package/UPSTREAM.json` record the Siril scripts
checkout the port follows and every intentional divergence, including the
NumPy convolution that replaces an unstable SciPy call. Check them against a
local clone with:

```bash
python3 tools/check_upstream.py \
  --package-dir packages/hdr_multiscale/package \
  --upstream-checkout ../siril-scripts
```

## Tests

```bash
python3 -m unittest discover -s packages/hdr_multiscale/tests
```

The parity tests load the upstream script from `SIRIL_SCRIPTS_CHECKOUT`, or
from `../siril-scripts`, and skip when it is absent.
