# Narrowband Normalization

Narrowband Normalization is an AfterNight port of Yannick Dutertre's
NarrowbandNormalization script for Siril, which implements Bill Blanshan and
Mike Cranfield's NarrowbandNormalization mathematics with Bill Blanshan's
permission.

It works on a stretched RGB image whose channels already hold the palette's
lines in its letter order (for SHO: red is SII, green is Ha, blue is OIII):

- scales OIII and SII toward Ha, with a boost for each line
- builds HOO's green from Ha and the normalized OIII in one of three blend modes
- reduces green with SCNR in the three-line palettes
- can take the result's lightness from the original image or from one line
- finishes with highlight reduction and a brightness stretch

The package registers one process, **Narrowband Normalization**, with RT
preview. It needs no Python dependencies beyond NumPy from AfterNight's shared
`scientific_core` profile.

This is a full hosted package (`sdk_backend = runtime`) under
GPL-3.0-or-later. It is source-staged (`"publish": false`): it validates and is
tested here but stays out of the repository index until its release gates in
`packaging/PUBLICATION_READINESS.md` are met.

## Provenance

`package/UPSTREAM.md` and `package/UPSTREAM.json` record the Siril scripts
checkout the port follows and every intentional divergence. Check them against
a local clone with:

```bash
python3 tools/check_upstream.py \
  --package-dir packages/narrowband_normalization/package \
  --upstream-checkout ../siril-scripts
```

## Tests

```bash
python3 -m unittest discover -s packages/narrowband_normalization/tests
```

The parity tests load the upstream script from `SIRIL_SCRIPTS_CHECKOUT`, or
from `../siril-scripts`, and skip when it is absent.
