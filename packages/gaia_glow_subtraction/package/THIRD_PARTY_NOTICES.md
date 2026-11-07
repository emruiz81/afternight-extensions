# Third-Party Notices

## Ported Source

This package contains an AfterNight port of a script from the Siril scripts
repository.

- Original script: GaiaGlowSubtraction for Siril, version 1.2.6
- Original author: Adrian Knagg-Baugh, (c) 2026 (aje.baugh@gmail.com)
- Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/GaiaGlowSubtraction.py
- Original license declared in the source file: GPL-3.0-or-later
- The script is an independent reimplementation of the functionality of the
  PixInsight tool PhotometricGlowSubtraction (deepskycolors.com), based only on
  its public documentation.

`gaia_glow_subtraction_core.py` carries the upstream script's lines 1-7400
(its numerical core) unchanged apart from the sirilpy import block; see
`UPSTREAM.md` for every intentional divergence.

## Python Dependencies

The package installs these public PyPI distributions from the hash-locked
`requirements.lock`; their wheels are downloaded by AfterNight during install
and are not redistributed in this package. NumPy and SciPy come from
AfterNight's bundled runtime.

| Distribution | Version | License |
| --- | --- | --- |
| astropy | 8.0.2 | BSD-3-Clause |
| astropy-healpix | 2.0.1 | BSD-3-Clause |
| astropy-iers-data | 0.2026.11.2.0.34.55 | BSD-3-Clause |
| certifi | 2026.10.23 | MPL-2.0 |
| charset-normalizer | 3.5.2 | MIT |
| idna | 3.20 | BSD-3-Clause |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| psutil | 7.2.2 | BSD-3-Clause |
| pyerfa | 2.0.1.5 | BSD-3-Clause |
| PyYAML | 6.0.3 | MIT |
| requests | 2.34.2 | Apache-2.0 |
| urllib3 | 2.8.0 | MIT |

## Catalogue Data

No catalogue data is bundled. At run time the package downloads, and caches in
the folder chosen in its settings:

- Gaia DR3 XP sampled spectra and positions in Siril's catalogue format, from
  the Siril catalogue mirror (https://zenodo.org/records/17988559). Gaia data:
  ESA/Gaia/DPAC (https://www.cosmos.esa.int/gaia).
- The Hipparcos main catalogue (ESA 1997, ESA SP-1200) stars brighter than
  V 4.2, through the CDS VizieR TAP service (catalogue I/239/hip_main).

Local Siril catalogues named in the settings are read in place.
