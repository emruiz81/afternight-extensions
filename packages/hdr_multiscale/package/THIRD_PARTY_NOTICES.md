# Third-Party Notices

This package contains an AfterNight port of a script from the Siril scripts
repository.

- Original script: HDR Multiscale for Siril, version 1.0.2
- Original authors: Franklin Marek (Seti Astro Suite, www.setiastro.com),
  adapted for Siril by Cyril Richard; (c) Cyril Richard 2025
- Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/HDR_multiscale.py
- Original license declared in the source file: GPL-3.0-or-later

`hdr_multiscale_core.py` carries the upstream core math, with its convolution
computed in NumPy; see `UPSTREAM.md` for every intentional divergence.

The package declares no Python dependencies of its own. It uses NumPy from
AfterNight's shared `scientific_core` profile and redistributes no third-party
wheels or binaries.
