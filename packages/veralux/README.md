# VeraLux Suite

VeraLux Suite is an AfterNight port/adaptation of Riccardo Paterniti's original
VeraLux Siril scripts. The package is intentionally suite-scoped: users install
one VeraLux extension package, and the individual VeraLux tools register as
separate AfterNight processes that share the same dependency environment and
requirements lock.

The staged processes are:

- VeraLux Revela, which enhances post-stretch local contrast and texture
  through a modified ATWT frequency-separation core while preserving a
  shadow/noise gate and optional stellar-profile protection.
- VeraLux Alchemy, which works in the linear domain to normalize Ha/OIII signal
  balance, optionally compensate OSC dual-band crosstalk, and mix HOO-style
  palettes before stretching.
- VeraLux HyperMetric Stretch, which applies a nonlinear inverse-hyperbolic
  tone mapping while preserving color vectors and offering ready-to-use or
  scientific output control.
- VeraLux Vectra, which performs selective LCH color-vector grading while
  preserving luminance and protecting neutral shadows and stellar cores.

The package remains source-staged with `publish: false` until release assets,
image-quality comparisons, and the full suite dependency policy are complete.

## Attribution

Original VeraLux scripts Copyright (c) 2025 Riccardo Paterniti.
AfterNight port Copyright (c) 2026 AfterNight contributors. The derived source
is distributed under GPL-3.0-or-later; see `package/UPSTREAM.md` for provenance.
