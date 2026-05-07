# Workflows

`validate.yml` is the repository gate for pull requests and pushes to `main`.
It:

- installs `zstd`
- runs package-tool unit tests
- builds published package source trees into deterministic `.tar.zst` assets
- skips source-staged packages marked with `"publish": false`
- verifies generated sidecar hashes against compressed assets
- regenerates `index.json` and diffs it against the checked-in file
- runs package-local tests in isolated virtual environments
- installs `packages/<extension_id>/tests/requirements.txt` when present
- clones the sibling AfterNight repository only to provide Python SDK import
  context for package tests

`build-assets.yml` is a manual workflow for producing package assets. It can
build:

- all currently published packages
- Cosmic Clarity by itself
- GraXpert's thin PyPI-backed asset without redistributing public wheels
- VeraLux Suite by itself

The workflow uploads `.tar.zst` files and sidecars as GitHub Actions artifacts.
It does not create a GitHub Release or modify `index.json` on its own.

`publish-release.yml` is the maintainer publication workflow. It runs from
`main`, validates the requested package id and version, rebuilds published
assets, verifies the checked-in index, creates the GitHub Release, and uploads
the selected package `.tar.zst` plus metadata sidecar.

Release publication should reuse the repository builder and index generator so
that compressed asset hashes in `index.json` match the exact released files.

See `../../docs/RELEASE_PROCESS.md` for the full contributor and maintainer
workflow.
