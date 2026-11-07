# Gaia Glow Subtraction

Gaia Glow Subtraction is an AfterNight port of GaiaGlowSubtraction for Siril
by Adrian Knagg-Baugh, an independent reimplementation of PixInsight's
PhotometricGlowSubtraction from its public documentation.

It subtracts the extended glow (scattering aureole) around bright stars from a
linear, plate-solved, stacked image with its stars. Each star's glow is its
flux, predicted from Gaia DR3 through a zero point calibrated on the image's
own unsaturated stars, times an extended PSF measured on the image. Stars
brighter than G = 4 take their flux from Hipparcos. Faint structure under the
glow is not part of the model and survives. Run it after plate solving and
before background extraction, colour calibration, deconvolution, star removal
and stretching.

The package registers one Apply-only process, **Gaia Glow Subtraction**. A run
can take a few minutes. The first run in a field downloads the Gaia catalogue
pieces it needs from the Siril catalogue mirror and caches them; the
extension settings choose the cache folder and can name local Siril
catalogues.

This is a full hosted package (`sdk_backend = runtime`) under
GPL-3.0-or-later. Its private environment installs Astropy, astropy-healpix,
requests and psutil from the hash-locked `package/requirements.lock`, with
NumPy and SciPy from AfterNight's runtime. It is source-staged
(`"publish": false`): it validates and is tested here but stays out of the
repository index until its release gates in
`packaging/PUBLICATION_READINESS.md` are met.

## Provenance

The numerical core is vendored unchanged from the upstream script;
`package/UPSTREAM.md` and `package/UPSTREAM.json` record the Siril scripts
checkout, the pixel conventions and every intentional divergence. Check them
against a local clone with:

```bash
python3 tools/check_upstream.py \
  --package-dir packages/gaia_glow_subtraction/package \
  --upstream-checkout ../siril-scripts
```

## Dependencies

Refresh the hash lock only when changing dependencies:

```bash
python3 packages/gaia_glow_subtraction/packaging/refresh_requirements_lock.py
```

## Tests

```bash
python3 -m pip install -r packages/gaia_glow_subtraction/tests/requirements.txt
python3 -m unittest discover -s packages/gaia_glow_subtraction/tests
```

The tests run the vendored pipeline end to end on synthetic plate-solved
fields, with the network blocked. The vendoring test reads the upstream script
from `SIRIL_SCRIPTS_CHECKOUT`, or from `../siril-scripts`, and skips when it is
absent.
