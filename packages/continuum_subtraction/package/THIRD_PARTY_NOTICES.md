# Third-Party Notices

This package contains an AfterNight port of a script from the Siril scripts
repository.

- Original script: Narrowband Continuum Subtraction for Siril, version v3.0.7
- Original authors: Adrian Knagg-Baugh, (c) 2025, and Dave Lindner, (c) 2025
- Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/ContinuumSubtraction.py
- Original license declared in the source file: GPL-3.0, so this package is
  distributed under GPL-3.0-only

`continuum_subtraction_core.py` carries the upstream estimate and arithmetic;
see `UPSTREAM.md` for every intentional divergence.

The package declares no Python dependencies of its own. It uses NumPy and SciPy
(`scipy.optimize.curve_fit`) from AfterNight's shared `scientific_core` profile
and redistributes no third-party wheels or binaries.
