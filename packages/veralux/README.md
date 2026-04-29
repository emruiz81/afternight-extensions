# VeraLux Suite

VeraLux Suite is an AfterNight port/adaptation of Riccardo Paterniti's original
VeraLux Siril scripts. The package is intentionally suite-scoped: users install
one VeraLux extension package, and the individual VeraLux tools register as
separate AfterNight processes that share the same dependency environment and
requirements lock.

The first staged process is VeraLux Revela, which enhances post-stretch local
contrast and texture through a modified ATWT frequency-separation core while
preserving a shadow/noise gate and optional stellar-profile protection. The
package remains source-staged with `publish: false` until release assets,
image-quality comparisons, and the full suite dependency policy are complete.

## Attribution

Original VeraLux Revela script Copyright (c) 2025 Riccardo Paterniti.
AfterNight port Copyright (c) 2026 AfterNight contributors. The derived source
is distributed under GPL-3.0-or-later; see `package/UPSTREAM.md` for provenance.
