# VeraLux Publication Readiness

Status: published as `veralux` version `0.1.1`.

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
  before the `0.1.0` release and confirmed outputs are visually sane in
  AfterNight. Version `0.1.1` changes the preview path only, so Apply output is
  unchanged and stays covered by the numerical regression metrics.
- Release signoff: maintainer release request accepted for version `0.1.0` on
  2026-05-07, and for version `0.1.1` on 2026-10-26.

## Version 0.1.1 Changes

- Each process declares its `preview_scaling`, and every process previews the
  whole image (`full_only`). Seven measure the whole image in every preview.
  Curves stays whole too: it divides a floating-point image whose brightest
  sample passes one down as counts, and a reduced frame can average that
  sample below one, so a `decimated` drag would preview another exposure than
  Apply gives.
- Nox keys its on-demand preview cache on the image's content, not only its
  size, so an image changed in place shows the current image until Update
  Preview is pressed, never the correction of an earlier image. The key is a
  CRC-32 of every sample, so a change to one pixel is seen.
- Nox cuts a manual protection mask that covers the whole image to the
  previewed part instead of resizing it onto the part.
- Nox's preview before its first update reads an image of integer samples in
  the range the correction is shown in, so it shows the image instead of
  white.
- StarComposer keys its cached stars proxy on the stars image's content and
  the frame's placement, so the preview composes the stars as Apply does after
  the stars view changes in place.

## Release Validation

Release validation for `0.1.1` used an isolated Python environment with the
host-provided scientific runtime dependency (`numpy`) plus the packages declared
in `package/requirements.lock`.

Commands run:

```bash
python -m unittest discover -s packages/veralux/tests
python -m unittest discover -s tests
python tools/check_veralux_upstream.py --upstream-checkout ../siril-scripts
VERALUX_UPSTREAM_CHECKOUT=../siril-scripts \
  python -m unittest packages/veralux/tests/test_veralux_upstream_quality.py
python tools/build_repository_assets.py --output-dir dist
python tools/generate_index.py \
  --packages-root packages \
  --assets-dir dist \
  --updated-at "$(python -c 'import json; print(json.load(open("index.json", encoding="utf-8"))["updated_at"])')" \
  --output index.json
```

## Representative QA Signoff

Manual release testing covered representative inputs for `0.1.0`:

- linear RGB data
- stretched RGB data
- narrowband or OSC dual-band data
- star-mask data for StarComposer
- starless plus stars workflow data when the host UI supports paired inputs

The maintainer confirmed the tested outputs are visually sane in AfterNight.
When future behavior differs from upstream Siril, document the intentional
difference in `package/QUALITY_VALIDATION.md` or release notes.
