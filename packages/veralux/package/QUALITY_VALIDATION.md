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
| Vectra | LCH vector engine output with local convolution tolerance | max abs <= 2e-4, mean abs <= 1e-5 |
| Curves | RGB/K curve output against upstream SciPy Akima LUT | mean abs <= 0.025, p95 <= 0.040, max abs <= 0.050 |

Curves intentionally uses a package-local Hermite/Akima-style interpolator
instead of depending on SciPy only for spline generation. The quality threshold
captures that expected interpolation difference while still bounding visible
drift against the upstream Siril result.

## First-Pass Intentional Divergences

The following first-pass processes are covered by deterministic local regression
metrics and by runtime-host execution smoke tests, but are not claimed as exact
Siril output parity yet:

| Tool | Reason exact output parity remains future work |
|---|---|
| Revela | Upstream exact comparison requires the OpenCV Lab/filter path; the package keeps OpenCV as the preferred runtime path and a NumPy fallback for diagnostics. |
| Nox | The native process uses the upstream Zenith sparse membrane solver when SciPy/OpenCV runtime dependencies are installed; remaining exact-output drift can come from AfterNight star profiling and host mask input replacing Siril's `list.lst` PSF file and PyQt brush/lasso mask image. |
| Silentium | The native process uses the upstream PyWavelets SWT/db2 thresholding path and SciPy edge morphology when runtime dependencies are installed; remaining exact-output drift can come from AfterNight star profiling versus Siril `findstar` list generation and the deliberate uniform wavelet-FWHM fallback used to keep native previews visibly responsive. |
| StarComposer | The native process now exposes the starless + stars/starmask workflow with RT preview; remaining exact-output drift can come from package-local NumPy blur/morphology helpers replacing OpenCV post-processing in minimal environments. |

These divergences are also listed in `UPSTREAM.md`. They are deliberate v1
scope choices, not silent algorithm changes. Future parity slices should add
fixture images and exact/near-exact checks here as the corresponding SDK and UI
capabilities land.
