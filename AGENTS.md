# AfterNight Extensions - Agent Guide

This guide is the working contract for automated agents in the
`afternight-extensions` repository. Keep it aligned with the repository docs and
tooling; when policy details conflict, treat `docs/` as canonical and update
this file to match.

## Mission

This repository contains the official curated extension package sources,
release metadata, validation tooling, and generated candidate repository index
consumed by AfterNight's Extension Manager.

The sibling application repository is expected at:

```text
../afternight
```

Use the sibling repository for AfterNight SDK/API context, app-side package
validator behavior, Extension Manager implementation details, and end-to-end
host/runtime tests.

## Current Repository Shape

- `packages/<extension_id>/package/` - source layout that becomes the package
  archive root
- `packages/<extension_id>/repository.json` - release metadata used to generate
  `index.json`
- `packages/<extension_id>/README.md` - package-specific author/user notes
- `packages/<extension_id>/tests/` - package tests; `requirements.txt` is
  optional when extra test dependencies are needed
- `packages/<extension_id>/packaging/` - package-specific lock/build/readiness
  metadata
- `docs/` - normative repository policy, package format, licensing, host-mode,
  and release workflow docs
- `tools/` - package validation, archive build, index generation, live-index,
  and release-metadata scripts
- `tests/` - repository tooling and policy tests
- `.github/workflows/` - validation, asset-preview, and maintainer publication
  workflows
- `index.json` - generated candidate repository index checked into `main`

Current publishable package ids are `cosmic_clarity`, `graxpert`, `rc_astro`,
and `veralux`. If a new publishable package is added, update
`.github/workflows/publish-release.yml` so the static `package_id` dropdown
matches the publishable package list; repository tests enforce this.

Do not commit release archives, generated metadata sidecars, `dist/` output,
generated virtual environments, caches, downloaded public wheels, secrets,
tokens, private URLs, or local absolute paths. Do not redistribute public PyPI
wheels in new extension packages.

## Canonical References

- `docs/PACKAGE_FORMAT.md` - archive layout, manifest schema, dependency
  metadata, repository metadata, and extraction policy
- `docs/HOST_MODES_AND_LICENSING.md` - `sdk_backend`, allowed imports, host
  process behavior, and license policy
- `docs/REPOSITORY_POLICY.md` - index, signatures, publication staging, binary
  and wheel policy
- `docs/RELEASE_PROCESS.md` - contributor validation, CI, and maintainer
  publication workflow
- `docs/LICENSING.md` - package license, notice, provenance, and publication
  blockers
- `packages/README.md` - package folder layout and repository-ready checklist

## Copilot Review Customization

GitHub Copilot code review on GitHub.com reads `.github/copilot-instructions.md`
and `.github/instructions/*.instructions.md`, not this file. Keep those review
instructions aligned with this guide and the canonical `docs/` references.
When policy details conflict, treat `docs/` as canonical and update the review
instruction files together with this guide.

## Package Rules

Every repository-ready package must have:

- `package/extension.json`
- package-local Python entry point declared by `entry_point`
- process declarations through `process_class` or `processes`, as appropriate
- `id`, `name`, `version`, `summary`, `author`, `license`, `publisher_id`,
  `type`, `entry_point`, `category`, `launch_mode`, and `sdk_backend`
- `package_format_version: 1`, `protocol_version: 1`, and `sdk_version: 1`
- package-local `LICENSE` matching the manifest license
- `THIRD_PARTY_NOTICES.md` when dependencies, models, helper binaries, bundled
  artifacts, or copied upstream code are included
- `repository.json` next to `package/` with release metadata or
  `"publish": false` staging
- package tests under `packages/<extension_id>/tests/`

Use current runtime target IDs:

- `linux-clang-x86_64`
- `windows-msvc-x86_64`

Pure Python packages may omit `runtime_targets` or publish one cross-target
asset. If a package includes extension-specific target artifacts such as private
wheels, custom `.pyd`/`.so` modules, shared libraries, helper binaries, or other
native artifacts, it must declare compatible `runtime_targets`.

Keep extension ids stable. Use lowercase snake-case or dotted identifiers that
pass AfterNight manifest validation. For package updates, bump
`extension.json.version` with SemVer when publishing user-visible changes and
keep `repository.json.latest_version` in sync.

## Host Modes And Licensing

Every package must declare `sdk_backend` explicitly.

- `runtime` is the full hosted mode for packages that use AfterNight Engine,
  `_afternight_runtime`, Engine-backed `afternight` modules, or native process
  controls. Runtime packages must use a GPL-3.0-family license.
- `protocol` is the lite hosted mode for packages that use app/view protocol
  services and own their UI or processing. Protocol packages must not import
  `_afternight_runtime`, Engine-backed `afternight` modules such as `core`,
  `io`, `registration`, `calibration`, or `stacking`, or the native
  `afternight.ui` surface. Use `afternight.ui_protocol` for protocol-safe UI
  helpers.
- `rpc` is reserved for future Engine SDK over RPC and is not publishable until
  the target AfterNight release ships RPC hosting support.

When an extension needs a new native AfterNight control, add it to the sibling
app as a generic reusable control. Do not use extension- or process-specific
names for app-side classes, ParamDef types, object names, files, or helpers;
keep process-specific wording in the extension schema/configuration.

## Provenance Rules

Derived works and ports should expose package provenance in `extension.json`:

- `attribution`
- `original_author`
- `original_project`
- `original_source_url`
- `upstream_commit`

VeraLux-derived packages must include all five fields plus package-local
`UPSTREAM.md` and `UPSTREAM.json`. Preserve licenses and notices when moving or
porting first-party package sources from `../afternight/extensions/` or any
upstream project.

## Dependency Rules

- Use hashed `requirements.lock` files when Python dependencies are declared.
- Set `dependencies.pip.require_hashes` to `true` when `requirements_file` is
  present.
- Every lock-file requirement must be exactly pinned with `==` and include at
  least one `--hash=sha256:` value.
- Use official PyPI indexes with pinned hashes for packages available from
  PyPI.
- Do not bundle public PyPI wheels inside package assets.
- Keep package-local `find_links` paths inside the package root, and use them
  only for extension-specific/private artifacts unavailable from official
  indexes.
- Use `shared_host` only for host-curated profiles such as `scientific_core`.
- Use `shared_group` only for related packages that intentionally share one
  dependency context.
- Packages that declare dependencies must include `THIRD_PARTY_NOTICES.md`.

Prefer one cross-target asset unless the package bundles real target-specific
artifacts. Official release assets are `.tar.zst`; build a deterministic tar
payload first, then compress it with zstd.

## Index And Releases

`main/index.json` is a generated candidate index used by CI and release
validation. It is generated from:

- package manifests in `packages/<extension_id>/package/extension.json`
- release metadata in `packages/<extension_id>/repository.json`
- compressed asset sidecars generated by `tools/build_package.py` or
  `tools/build_repository_assets.py`

Do not hand-edit package entries in `index.json`. Update package source or
`repository.json`, build assets, regenerate the index, and commit the resulting
metadata when a published package changes.

The client-facing live feed is published only by the maintainer workflow to the
`live` branch after GitHub Release assets exist and download URLs are verified.

For every release asset:

- `package_hash` is mandatory and authoritative
- hash the downloadable `.tar.zst` asset, not the intermediate uncompressed tar
- official migration assets may use `signature_state: "unsigned"`
- emit `signature_state: "verified"` only from signed asset sidecars generated
  by `tools/sign_repository_assets.py` and verified by the maintainer workflow
- `signature_state: "failed"` blocks installation

The generated index describes the current publishable release for each package.
Older archives remain available on their GitHub Release tags, but current
tooling does not rebuild or preserve historical release entries from older
source versions.

Use `"publish": false` in `repository.json` for source-staged packages that
should validate locally but stay out of generated assets and indexes.

## Validation

The package builder requires `zstd` on `PATH`. Examples use POSIX-style
`python3`; on Windows, use the local interpreter alias that works in the
environment.

Run repository tooling tests:

```bash
python3 -m pip install --require-hashes -r tools/quality/requirements.lock
python3 -m ruff format --check .
python3 -m ruff check .
python3 -m unittest discover -s tests
```

Build all currently published package assets and verify the checked-in candidate
index:

```bash
python3 tools/build_repository_assets.py --output-dir dist
python3 tools/generate_index.py \
  --packages-root packages \
  --assets-dir dist \
  --updated-at "$(python3 -c 'import json; print(json.load(open("index.json", encoding="utf-8"))["updated_at"])')" \
  --output /tmp/index.json
diff -u index.json /tmp/index.json
```

Build one package asset when working on a single package:

```bash
python3 tools/build_package.py packages/<extension_id>/package --output-dir dist
```

Run package tests locally after installing optional test dependencies:

```bash
python3 -m unittest discover -s packages/<extension_id>/tests
```

Package-local tests may import the AfterNight Python SDK modules from
`../afternight/python/modules`. GitHub Actions currently runs repository
tooling tests and index validation; package-local tests should still be run
locally when changing package behavior.

Use the sibling AfterNight test binary when you need to verify client-side
Extension Manager behavior after building it:

```bash
cd ../afternight
make -C build/make-linux/tests -j4 Test_ProcessFramework
LD_LIBRARY_PATH=bin/clang/release ./bin/clang/release/Test_ProcessFramework --gtest_filter='ExtensionManagerTest.PackageValidatorAcceptsBundledReferenceExtensions:ExtensionManagerTest.ExternalExtensionRepositoryPassesAppSidePackageValidator:ExtensionManagerTest.OfficialRepositoryIndexUrlUsesLivePublishedFeed'
```

## Editing Guidance

- Keep package diffs scoped to the package being changed.
- Keep repository policy, docs, package metadata, generated index changes, and
  workflow dropdown changes in sync when they are part of the same repository
  behavior.
- Do not rewrite generated package archives by hand.
- Prefer deterministic packaging: sorted entries, stable tar metadata, pinned
  hashes, and generated sidecars.
- Use structured JSON tooling/parsers for manifests, repository metadata, and
  index data instead of ad hoc string manipulation.
- When changing Python code, repository tooling, tests, or Python validation
  config, agents must run the Ruff format and lint checks locally before
  finishing or explicitly call out why they could not.
- Use ASCII by default.

## Definition Of Done

A package or repository change is ready when:

- Python format and lint checks pass when Python files or validation config
  change
- manifests validate
- repository tooling tests pass
- relevant package tests pass locally or are explicitly called out if skipped
- generated index metadata is updated or confirmed unchanged
- release assets, if produced, hash-match the index sidecars and generated
  package hashes
- dependency locks are hashed and bundled artifacts are target-specific where
  needed
- license, notice, and provenance files are present
- docs are updated for any new package, process, host-mode behavior, or release
  workflow change
- new publishable packages are present in the publish workflow dropdown
