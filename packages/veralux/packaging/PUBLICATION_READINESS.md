# VeraLux Publication Readiness

Status: published as `veralux` version `0.1.0`.

The package is included in the official repository index. The release asset is
hash-pinned in `index.json` and uses `signature_state: "unsigned"` until package
signing is implemented.

## Completed Gates

- Suite package layout: one `veralux` package registers the eight VeraLux
  processes, with one shared dependency environment and requirements lock.
- Provenance: `package/UPSTREAM.json`, `package/UPSTREAM.md`, package license,
  and third-party notices identify the upstream VeraLux sources and GPL terms.
- Package smoke: deterministic archive build contains one VeraLux suite root,
  all expected process modules, `STARTING_POINT.md`, `UPSTREAM.json`,
  `QUALITY_VALIDATION.md`, and notices.
- Automated quality checks: package-local tests cover process adapters,
  numerical regression metrics, and upstream quality parity for the ported
  VeraLux algorithms.
- Upstream provenance: `tools/check_veralux_upstream.py` verifies the captured
  VeraLux baseline against the local `siril-scripts` checkout.
- Host integration checks: the main AfterNight host tests exercise VeraLux
  process discovery, native parameter schemas, runtime host execution, and
  large NumPy image round-trips.
- Representative real-image visual QA: maintainer manual testing completed
  before release and confirmed outputs are visually sane in AfterNight.
- Release signoff: maintainer release request accepted for version `0.1.0` on
  2026-05-07.

## Release Validation

Release validation for `0.1.0` used an isolated Python environment with the
host-provided scientific runtime dependency (`numpy`) plus the packages declared
in `package/requirements.lock`.

Commands run:

```bash
python -m unittest discover -s packages/veralux/tests
python -m unittest tests/test_package_tools.py tests/test_veralux_upstream_tools.py
python tools/check_veralux_upstream.py --upstream-checkout ../siril-scripts
VERALUX_UPSTREAM_CHECKOUT=../siril-scripts \
  python -m unittest packages/veralux/tests/test_veralux_upstream_quality.py
python tools/build_package.py packages/veralux/package --output-dir dist-veralux
python tools/generate_index.py \
  --packages-root packages \
  --assets-dir dist \
  --updated-at 2026-05-07T02:30:30Z \
  --output index.json
```

## Representative QA Signoff

Manual release testing covered representative:

- linear RGB data
- stretched RGB data
- narrowband or OSC dual-band data
- star-mask data for StarComposer
- starless plus stars workflow data when the host UI supports paired inputs

The maintainer confirmed the tested outputs are visually sane in AfterNight.
When future behavior differs from upstream Siril, document the intentional
difference in `package/QUALITY_VALIDATION.md` or release notes.
