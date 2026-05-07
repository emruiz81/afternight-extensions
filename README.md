# AfterNight Extensions

Official curated extension repository for AfterNight.

This repository contains extension package source trees, package release metadata,
repository validation tools, deterministic asset builders, and the generated
`index.json` consumed by AfterNight's Extension Manager.

## Published Packages

The generated `index.json` currently publishes:

- Cosmic Clarity: a pure-Python AfterNight adapter for Seti Astro's Cosmic
  Clarity denoise, dark-star, sharpening, and super-resolution workflows. The
  upstream Cosmic Clarity executables and model payloads are not redistributed
  here.
- GraXpert AI: a thin AfterNight adapter for GraXpert background extraction,
  denoise, and deconvolution. GraXpert and public dependency wheels are
  installed by the host from hash-locked PyPI requirements during install.

The repository also contains source-staged packages that are reviewed and tested
in git but intentionally omitted from `index.json` until their release gates are
complete. VeraLux Suite is currently source-staged with `"publish": false` in
`packages/veralux/repository.json`.

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
|-- docs/                      # package format, policy, and licensing docs
|-- tools/                     # validation, asset build, and index tools
|-- tests/                     # repository tooling tests
`-- .github/workflows/         # CI and manual asset-build workflows
```

Package source belongs in `packages/<extension_id>/package/`. Built archives,
generated sidecars, wheel downloads, virtual environments, caches, and other
release outputs should not be committed.

## Package Assets

AfterNight extension release assets are zstd-compressed tar archives
(`.tar.zst`). Each archive extracts to exactly one package root containing
`extension.json`.

Pure Python packages and packages whose dependencies are resolved from official
package indexes normally publish one cross-target asset. Packages that bundle
extension-specific native artifacts, helper binaries, private wheels, models, or
target-specific libraries should publish target-specific assets for the runtime
targets they support:

- `linux-clang-x86_64`
- `windows-msvc-x86_64`

Public PyPI wheels must stay out of package assets. Use explicit PyPI indexes
and hash-locked `requirements.lock` files instead.

## Repository Index

`index.json` is generated from:

- `packages/<extension_id>/package/extension.json`
- `packages/<extension_id>/repository.json`
- `.tar.zst.metadata.json` sidecars produced by `tools/build_package.py`

Do not hand-edit package entries in `index.json`. Update package source or
release metadata, rebuild deterministic assets, regenerate the index, and review
the diff.

Every release asset in the index must declare a SHA-256 `package_hash` for the
compressed `.tar.zst` file. Official unsigned packages use
`signature_state: "unsigned"` and are hash-verified before extraction.
`signature_state: "verified"` is reserved for a future signing flow.

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

Package-specific tests live under `packages/<extension_id>/tests/`. Some
package tests require the package runtime dependencies declared by the package
manifest and lock files; package READMEs or `packaging/` notes should document
that setup when it differs from the repository tooling tests.

## Adding Or Updating Packages

Every publishable package must include:

- `extension.json` at the package root
- a package-local Python entry point declared by `entry_point`
- `summary`, `description`, `author`, `license`, and `publisher_id`
- `package_format_version: 1`, `protocol_version: 1`, and `sdk_version: 1`
- `LICENSE`
- `THIRD_PARTY_NOTICES.md` when dependencies, models, helper binaries, copied
  upstream code, or bundled artifacts are included
- tests or validation coverage appropriate to the package risk

Use `packages/<extension_id>/repository.json` for release-only metadata such as
minimum app version, changelog text, publication timestamp, asset base URL, and
signature state. Set `"publish": false` when a package should remain
source-staged and absent from the public index.

## Licensing

The repository tooling, documentation, and AfterNight-maintained adapter code are
distributed under GPL-3.0 unless a file or package says otherwise. See
`LICENSE` for the GPL-3.0 text and `docs/LICENSING.md` for the package license
summary.

Each package also carries package-local licensing:

- Cosmic Clarity adapter: GPL-3.0. Upstream Cosmic Clarity executables, models,
  and runtime payloads are not bundled.
- GraXpert AI adapter: GPL-3.0. GraXpert and public dependency wheels are
  resolved from PyPI by the host and are not redistributed in the package asset.
- VeraLux Suite: GPL-3.0-or-later derived from Riccardo Paterniti's VeraLux
  Siril scripts, with provenance in `packages/veralux/package/UPSTREAM.md` and
  `packages/veralux/package/UPSTREAM.json`.

Unclear ownership, missing license metadata, incompatible terms, secrets, local
machine paths, or private download URLs block publication.

## Related Repository

AfterNight application and SDK source live in the main repository:

```text
https://github.com/emruiz81/afternight
```

This extension repository provides package/index artifacts; the main app
repository implements the Extension Manager client, package validation, install
flow, and runtime host integration.
