# VeraLux Quality Validation

This package includes automated upstream comparison coverage for the parts of
the VeraLux Siril scripts that can be exercised as deterministic array cores
without a live Siril session.

The comparison test is:

```bash
VERALUX_UPSTREAM_CHECKOUT=/path/to/siril-scripts \
python3 -m unittest packages/veralux/tests/test_veralux_upstream_quality.py
```

When `VERALUX_UPSTREAM_CHECKOUT` is not set, the test uses the sibling
`../siril-scripts` checkout if it exists. The test imports the captured upstream
scripts with minimal `sirilpy` and PyQt stubs, then compares package outputs to
the original core functions on deterministic synthetic RGB fixtures.

## Automated Upstream Checks

| Tool | Upstream comparison | Threshold |
|---|---|---|
| Alchemy | Exact worker-core output for classic and Quantum Unmix paths | max abs <= 2e-6, mean abs <= 2e-7 |
| HyperMetric Stretch | Exact `process_veralux_v6` ready-to-use output | max abs <= 1e-7, mean abs <= 1e-8 |
| Vectra | LCH vector engine output, including Shadow Authority and star protection | exact within float tolerance when SciPy is installed; fallback max abs <= 2e-4, mean abs <= 1e-5 |
| Curves | RGB/K and Luminance curve output against upstream SciPy Akima/OpenCV paths | max abs <= 2e-6, mean abs <= 2e-7 |
| StarComposer | Shaped star-layer output, including optical-healing post-surgery range | max abs <= 2e-6, mean abs <= 2e-7 |

Curves uses SciPy's `Akima1DInterpolator` and OpenCV Lab/HSV conversion when
the declared runtime dependencies are installed, matching the upstream Siril
core. Package-local NumPy paths remain as minimal diagnostic fallbacks only.
Whenever a VeraLux process has to use one of those lower-quality fallback paths
because an optional runtime library failed to load, the adapter emits a warning
to the AfterNight console log and names the missing dependency.

## First-Pass Intentional Divergences

The following first-pass processes are covered by deterministic local regression
metrics and by runtime-host execution smoke tests, but are not claimed as exact
Siril output parity yet:

| Tool | Reason exact output parity remains future work |
|---|---|
| Revela | Upstream exact comparison requires the OpenCV Lab/filter path; the package keeps OpenCV as the preferred runtime path and a NumPy fallback for diagnostics. |
| Nox | The native process uses the upstream Zenith sparse membrane solver when SciPy/OpenCV runtime dependencies are installed; remaining exact-output drift can come from AfterNight star profiling and host mask input replacing Siril's `list.lst` PSF file and PyQt brush/lasso mask image. |
| Silentium | The native process uses the upstream PyWavelets SWT/db2 thresholding path and SciPy edge morphology when runtime dependencies are installed; remaining exact-output drift can come from AfterNight star profiling and FWHM-map generation versus Siril `findstar`/`list.lst` side effects. |
| StarComposer | The native process now exposes the starless + stars/starmask workflow with RT preview; exact shaping is covered when OpenCV is installed, with package-local NumPy blur/morphology helpers retained only for minimal environments. |

These divergences are also listed in `UPSTREAM.md`. They are deliberate v1
scope choices, not silent algorithm changes. Future parity slices should add
fixture images and exact/near-exact checks here as the corresponding SDK and UI
capabilities land.
