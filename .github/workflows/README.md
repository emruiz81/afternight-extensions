# Workflows

`validate.yml` is the repository gate for pull requests and pushes to `main`.
It:

- installs `zstd`
- runs package-tool unit tests
- builds published package source trees into deterministic `.tar.zst` assets
- skips source-staged packages marked with `"publish": false`
- verifies generated sidecar hashes against compressed assets
- regenerates `index.json` and diffs it against the checked-in file

`build-assets.yml` is a manual workflow for producing package assets. It can
build:

- all currently published packages
- Cosmic Clarity by itself
- GraXpert's thin PyPI-backed asset without redistributing public wheels

The workflow uploads `.tar.zst` files and sidecars as GitHub Actions artifacts.
It does not create a GitHub Release or modify `index.json` on its own.

Release publication should reuse the repository builder and index generator so
that compressed asset hashes in `index.json` match the exact released files.
