# Continuum Subtraction

Continuum Subtraction is an AfterNight port of Narrowband Continuum Subtraction
for Siril by Adrian Knagg-Baugh and Dave Lindner. It isolates line emission,
such as the HII regions of a galaxy, by removing the broadband continuum from a
narrowband image.

The package registers two processes:

- **Continuum Subtraction**, on a linear mono narrowband image: subtracts
  c x continuum, where the continuum is another open mono view registered to
  it (for Ha, usually the extracted red channel). c is estimated by minimizing
  the result's average absolute deviation over a region you paint around the
  subject, with the upstream coarse scan, fine scan and smooth-V fit, or set by
  hand.
- **Continuum Blend**, on a linear RGB image: adds a continuum-subtracted line,
  median-centred, into the channels with a strength and per-channel weights
  (Ha into red, SII into green, OIII into blue, or custom).

The estimate assumes the line emission does not follow the continuum's
structure; emission lying on it is partly subtracted with it. Paint a generous
region that holds the subject's continuum.

Both processes have RT preview and need no Python dependencies beyond NumPy
and SciPy from AfterNight's shared `scientific_core` profile.

This is a full hosted package (`sdk_backend = runtime`) under GPL-3.0-only, as
the upstream script is GPL-3.0. It is source-staged (`"publish": false`): it
validates and is tested here but stays out of the repository index until its
release gates in `packaging/PUBLICATION_READINESS.md` are met.

## Provenance

`package/UPSTREAM.md` and `package/UPSTREAM.json` record the Siril scripts
checkout the port follows and every intentional divergence. Check them against
a local clone with:

```bash
python3 tools/check_upstream.py \
  --package-dir packages/continuum_subtraction/package \
  --upstream-checkout ../siril-scripts
```

## Tests

```bash
python3 -m unittest discover -s packages/continuum_subtraction/tests
```

The parity tests load the upstream script from `SIRIL_SCRIPTS_CHECKOUT`, or
from `../siril-scripts`, and skip when it is absent.
