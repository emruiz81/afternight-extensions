# AfterNight Extensions

Official curated extension repository for AfterNight.

This repository stores package source trees, release metadata, validation and
build tooling, and the generated `index.json` consumed by AfterNight's
Extension Manager.

## Start Here

Use these entry points depending on what you need to do:

| Task | Read first |
| --- | --- |
| Understand the documentation set | [docs/README.md](docs/README.md) |
| Add or update a package | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Check package layout expectations | [packages/README.md](packages/README.md) |
| Review package schema and release metadata | [docs/PACKAGE_FORMAT.md](docs/PACKAGE_FORMAT.md) |
| Choose `sdk_backend` or review host-mode rules | [docs/HOST_MODES_AND_LICENSING.md](docs/HOST_MODES_AND_LICENSING.md) |
| Review licensing and publication blockers | [docs/LICENSING.md](docs/LICENSING.md) |
| Understand release and CI workflow | [docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md) |

## Published Packages

The generated `index.json` currently publishes:

- Cosmic Clarity: a pure-Python AfterNight adapter for Seti Astro's Cosmic
  Clarity denoise, dark-star, sharpening, and super-resolution workflows. The
  upstream executables and model payloads are not redistributed here.
- GraXpert AI: a thin AfterNight adapter for GraXpert background extraction,
  denoise, and deconvolution. GraXpert and public dependency wheels are
  installed by the host from hash-locked PyPI requirements during install.
- VeraLux Suite: a GPL-3.0-or-later AfterNight port of Riccardo Paterniti's
  VeraLux Siril scripts, published as one suite package that registers Revela,
  Alchemy, HyperMetric Stretch, Curves, Nox, Silentium, Vectra, StarComposer,
  and the Starting Point workflow guide.

## Repository Layout

```text
.
|-- index.json                 # generated repository index
|-- packages/                  # one folder per extension package
|   `-- <extension_id>/
|       |-- package/           # release archive root source
|       |   |-- extension.json
|       |   |-- <entry_point>.py
|       |   |-- requirements.lock
|       |   |-- LICENSE
|       |   `-- THIRD_PARTY_NOTICES.md
|       |-- README.md
|       |-- tests/
|       |-- packaging/
|       `-- repository.json    # release metadata outside the archive
|-- docs/                      # normative package and repository docs
|-- tools/                     # validation, asset build, and index tools
|-- tests/                     # repository tooling tests
`-- .github/workflows/         # CI and manual asset-build workflows
```

Package source belongs in `packages/<extension_id>/package/`. Built archives,
generated sidecars, wheel downloads, virtual environments, caches, and other
release outputs should not be committed.

## Repository Model

- Extension release assets are zstd-compressed tar archives (`.tar.zst`).
- `index.json` is generated from package manifests, `repository.json`, and
  asset sidecars.
- Public PyPI wheels must not be redistributed in package assets.
- `"publish": false` in `repository.json` keeps a package source-staged and out
  of the public index.

Use [docs/PACKAGE_FORMAT.md](docs/PACKAGE_FORMAT.md) and
[docs/REPOSITORY_POLICY.md](docs/REPOSITORY_POLICY.md) for the full repository
and package rules.

## Validate Locally

The package builder requires `zstd` on `PATH`.

```bash
python3 -m unittest discover -s tests
python3 tools/build_repository_assets.py --output-dir dist
python3 tools/generate_index.py \
  --packages-root packages \
  --assets-dir dist \
  --updated-at "$(python3 -c 'import json; print(json.load(open("index.json", encoding="utf-8"))["updated_at"])')" \
  --output /tmp/index.json
diff -u index.json /tmp/index.json
```

To build one package asset:

```bash
python3 tools/build_package.py packages/<extension_id>/package --output-dir dist
```

Package-specific tests live under `packages/<extension_id>/tests/`. See the
package README or `packaging/` notes when a suite needs extra test-time
dependencies or sibling-repository SDK imports.

## Related Repositories

This extension repository provides package and index artifacts for public
distribution.

The main AfterNight application and SDK source are maintained separately from
this repository. References in package tests and authoring docs to a sibling
`../afternight` checkout mean a local app-source checkout when that code is
available to you.

## Release Flow

Contributor PRs carry source, tests, metadata, and generated `index.json`
changes. CI validates the repository and package-local tests, but it does not
publish GitHub Releases from PRs.

After a PR is merged, a maintainer runs the `Publish Extension Release` GitHub
Actions workflow from `main` with the package id and version.

See [docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md) for the full contributor
and maintainer workflow.
