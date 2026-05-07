# Workflows

Use the workflows for different purposes:

- `validate.yml`: automatic gate on pull requests and pushes. It rebuilds published assets only to verify repository consistency; it does not publish anything.
- `build-assets.yml`: manual packaging preview. It builds archives and uploads temporary GitHub Actions artifacts for inspection; it does not create a GitHub Release.
- `publish-release.yml`: manual maintainer publication path. It is the only workflow that creates or updates the official GitHub Release for a package version.

`validate.yml` is the repository gate for pull requests and pushes to `main`.
It:

- installs `zstd`
- runs package-tool unit tests
- builds published package source trees into deterministic `.tar.zst` assets
- skips source-staged packages marked with `"publish": false`
- verifies generated sidecar hashes against compressed assets
- regenerates `index.json` and diffs it against the checked-in file

Package-local tests are currently disabled in GitHub Actions because they
depend on a sibling `afternight` SDK checkout. Run those suites locally against
a sibling checkout when needed.

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

This is the only workflow that publishes downloadable release assets for users.

Release publication should reuse the repository builder and index generator so
that compressed asset hashes in `index.json` match the exact released files.

See `../../docs/RELEASE_PROCESS.md` for the full contributor and maintainer
workflow.
