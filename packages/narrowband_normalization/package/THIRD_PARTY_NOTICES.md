# Third-Party Notices

This package contains an AfterNight port of a script from the Siril scripts
repository.

- Original script: NarrowbandNormalization for Siril, version 1.0.5
- Original author: Yannick Dutertre (Cuiv), cuivlazygeek@gmail.com
- Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/NarrowbandNormalization.py
- Original license declared in the source file: GPL-3.0-or-later
- Underlying method: Bill Blanshan and Mike Cranfield's NarrowbandNormalization
  PixInsight script (https://cosmicphotons.com/scripts/). The Siril script is a
  clean-room implementation of its mathematics, made with Bill Blanshan's
  permission.

`narrowband_normalization_core.py` carries the upstream engine unchanged apart
from input normalization; see `UPSTREAM.md` for every intentional divergence.

The package declares no Python dependencies of its own. It uses NumPy from
AfterNight's shared `scientific_core` profile and redistributes no third-party
wheels or binaries.
