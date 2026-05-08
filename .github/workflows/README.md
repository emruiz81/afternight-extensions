# Workflows

Use the workflows for different purposes:

- `validate.yml`: automatic gate on pull requests and pushes. It rebuilds published assets only to verify repository consistency; it does not publish anything.
- `build-assets.yml`: manual packaging preview. It builds archives and uploads temporary GitHub Actions artifacts for inspection; it does not create a GitHub Release.
- `publish-release.yml`: manual maintainer publication path. It is the only workflow that creates or updates the official GitHub Release for a package version and the client-facing live index.

`validate.yml` is the repository gate for pull requests and pushes to `main`.
It:

- installs `zstd`
- installs pinned Ruff and checks Python formatting and lint
- runs package-tool unit tests
- builds published package source trees into deterministic `.tar.zst` assets
- skips source-staged packages marked with `"publish": false`
- verifies generated sidecar hashes against compressed assets
- regenerates the candidate `index.json` and diffs it against the checked-in file

Package-local tests are currently disabled in GitHub Actions because they
depend on a sibling `afternight` SDK checkout. Run those suites locally against
a sibling checkout when needed.

The checked-in `main/index.json` is not the Extension Manager's production feed.
It is review and reproducibility metadata. Clients consume
`https://raw.githubusercontent.com/emruiz81/afternight-extensions/live/index.json`,
which is updated by `publish-release.yml` only after release assets are uploaded
and their download URLs have been checked.

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
assets, verifies the checked-in candidate index, creates or updates the GitHub
Release, uploads the selected package `.tar.zst` plus metadata sidecar, merges
the selected package into the live index, verifies the live index download URLs,
and publishes `index.json` to the `live` branch.

This is the only workflow that publishes downloadable release assets and makes
new versions visible to users. It also writes a run summary listing the
publishable package ids plus their declared release versions discovered from
`packages/*/repository.json`. The GitHub dispatch form itself can only show a
static package dropdown, so version discovery remains in the run summary. Pull
requests that add a new publishable package must update that dropdown;
repository tests fail if the workflow list falls out of sync.

Publish runs are serialized to avoid `live` branch races. Re-running a release
is idempotent when the existing uploaded assets byte-match the rebuilt files.
Draft releases can be promoted by re-running the same package/version with
`draft` disabled; mismatched existing assets still require
`replace_existing_assets=true`.

Release publication should reuse the repository builder and index generator so
that compressed asset hashes in `index.json` match the exact released files.

See `../../docs/RELEASE_PROCESS.md` for the full contributor and maintainer
workflow.
