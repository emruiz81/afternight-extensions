# VeraLux Publication Readiness

Status: source-staged, not publishable yet.

Keep `"publish": false` in `packages/veralux/repository.json` until every
release gate below is complete and the built package asset is available as a
hash-verified release asset.

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
- Host integration checks: the main AfterNight Phase 9 tests exercise VeraLux
  process discovery, native parameter schemas, runtime host execution, and
  large NumPy image round-trips.

## Remaining Publication Blocker

- [ ] Representative real-image visual QA and release signoff.

Before removing `publish: false`, run the built VeraLux package against an
approved real-image QA set that covers at least:

- linear RGB data
- stretched RGB data
- narrowband or OSC dual-band data
- star-mask data for StarComposer
- starless plus stars workflow data when the host UI supports paired inputs

For the signoff, capture the input set, process settings, output artifacts, and
review notes. The review must confirm that outputs are visually sane in
AfterNight and that any known differences from upstream Siril behavior are
intentional and documented in `package/QUALITY_VALIDATION.md` or release notes.

## Release Checklist

1. Run package tests:

   ```bash
   python3 -m unittest discover -s packages/veralux/tests
   python3 -m unittest tests/test_package_tools.py tests/test_veralux_upstream_tools.py
   ```

2. Verify upstream provenance and quality parity with the local Siril scripts
   checkout:

   ```bash
   python3 tools/check_veralux_upstream.py --upstream-checkout /path/to/siril-scripts
   VERALUX_UPSTREAM_CHECKOUT=/path/to/siril-scripts \
     python3 -m unittest packages/veralux/tests/test_veralux_upstream_quality.py
   ```

3. Build the deterministic release asset:

   ```bash
   python3 tools/build_package.py packages/veralux/package --output-dir dist-veralux
   ```

4. Publish the `.tar.zst` asset and sidecar metadata as release assets.
5. Record the release asset URL in release metadata if needed.
6. Remove `"publish": false` from `packages/veralux/repository.json`.
7. Regenerate and review the repository index:

   ```bash
   python3 tools/generate_index.py \
     --packages-root packages \
     --assets-dir dist-veralux \
     --updated-at <release timestamp> \
     --output index.json
   ```
