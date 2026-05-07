# VeraLux Suite

VeraLux Suite is an AfterNight port/adaptation of Riccardo Paterniti's original
VeraLux Siril scripts. The package is intentionally suite-scoped: users install
one VeraLux extension package, and the individual VeraLux tools register as
separate AfterNight processes that share the same dependency environment and
requirements lock.

The original VeraLux Starting Point script is adapted as
`package/STARTING_POINT.md`. It is a workflow guide rather than a process, and
documents the recommended order for applying the suite inside AfterNight.

The suite registers these processes:

- VeraLux Revela, which enhances post-stretch local contrast and texture
  through a modified ATWT frequency-separation core while preserving a
  shadow/noise gate and optional stellar-profile protection.
- VeraLux Alchemy, which works in the linear domain to normalize Ha/OIII signal
  balance, optionally compensate OSC dual-band crosstalk, and mix HOO-style
  palettes before stretching.
- VeraLux HyperMetric Stretch, which applies a nonlinear inverse-hyperbolic
  tone mapping while preserving color vectors and offering ready-to-use or
  scientific output control.
- VeraLux Curves, which applies Akima-style photometric curve sculpting across
  RGB/K, channel, luminance, chrominance, and saturation domains with optional
  luminance-range masking.
- VeraLux Nox, which estimates and removes broad additive gradients while
  protecting stars, nebulosity, and other high-confidence signal.
- VeraLux Silentium, which suppresses linear-stage luminance and chroma noise
  with multiscale thresholding, shadow-domain smoothing, and signal/highlight
  protection.
- VeraLux Vectra, which performs selective LCH color-vector grading while
  preserving luminance and protecting neutral shadows and stellar cores.
- VeraLux StarComposer, which shapes a selected stars/star-mask image with the
  upstream rational tone-mapping core and recomposes it onto the active
  starless target.

Recommended order:

```text
Nox -> Silentium -> Alchemy -> HyperMetric Stretch -> Curves -> Revela -> Vectra -> StarComposer
```

The package is published through the official AfterNight extension index.
Release validation and signoff notes are documented in
`packaging/PUBLICATION_READINESS.md`. Automated upstream quality coverage and
known first-pass parity limits are documented in `package/QUALITY_VALIDATION.md`.

The broader extension-author porting notes for this suite are captured in
`../../docs/VERALUX_PORTING_CASE_STUDY.md`.

## Attribution

Original VeraLux scripts Copyright (c) 2025 Riccardo Paterniti.
AfterNight port Copyright (c) 2026 AfterNight contributors. The derived source
is distributed under GPL-3.0-or-later; see `package/UPSTREAM.md` for provenance.
