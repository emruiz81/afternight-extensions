# AfterNight Extensions - Agent Guide

This file is the source of truth for automated agents and contributors working in the `afternight-extensions` repository.

## Mission

This repository contains the official curated extension package sources and generated repository metadata consumed by AfterNight's Extension Manager.

The sibling application repository is expected at:

```text
../afternight
```

Use the sibling repository for AfterNight SDK/API context, package-validator behavior, and Extension Manager implementation details.

## Repository Shape

- `packages/<extension_id>/package/` - source layout that becomes the package archive root
- `packages/<extension_id>/README.md` - package-specific author/user notes
- `packages/<extension_id>/tests/` - package tests
- `packages/<extension_id>/packaging/` - package-specific lock/build metadata
- `docs/` - repository policy, package format, contribution docs
- `tools/` - package validation, archive build, and index generation scripts
- `index.json` - generated/published repository index

Do not commit release archives, generated virtual environments, caches, or heavyweight wheel blobs unless a maintainer explicitly decides a package-local wheelhouse for extension-specific/private artifacts must be source-controlled. Do not redistribute public PyPI wheels in new extension packages.

## Package Rules

Every publishable package must have:

- `extension.json` at the package root
- package-local Python entry point declared by `entry_point`
- `summary`, `author`, `license`, and `publisher_id`
- `package_format_version: 1`, `protocol_version: 1`, and `sdk_version: 1`
- `LICENSE`
- `THIRD_PARTY_NOTICES.md` when dependencies, models, helper binaries, or copied upstream code are included

Use current runtime target IDs:

- `linux-clang-x86_64`
- `windows-msvc-x86_64`

If a package includes extension-specific target artifacts such as private wheels, custom `.pyd`/`.so` modules, shared libraries, or helper binaries, it must declare compatible `runtime_targets`.

## Dependency Rules

- Use hashed `requirements.lock` files when Python dependencies are declared.
- Set `dependencies.pip.require_hashes` to `true` when `requirements_file` is present.
- Use official PyPI indexes with pinned hashes for packages that are available from PyPI.
- Keep package-local `find_links` paths inside the package root, and use them only for extension-specific/private artifacts unavailable from official indexes.
- Prefer one cross-target asset unless the package bundles real target-specific artifacts.
- Official release assets are `.tar.zst`; build a deterministic tar payload first, then compress it with zstd.
- Use `shared_host` only for host-curated profiles such as `scientific_core`.
- Use `shared_group` only for related packages that intentionally share one dependency context.

## Index And Releases

`index.json` is the global metadata source consumed by AfterNight. It must be generated from package/release metadata, not hand-edited once tooling exists.

For every release asset:

- `package_hash` is mandatory and authoritative
- hash the downloadable `.tar.zst` asset, not the intermediate uncompressed tar
- official launch assets may use `signature_state: "unsigned"`
- do not emit `signature_state: "verified"` until real signing and verification exist
- `signature_state: "failed"` blocks installation

## Validation

Prefer repository-local tooling for Phase 6 package-repository work:

```bash
python3 -m unittest discover -s tests
python3 tools/build_package.py packages/<extension_id>/package --output-dir dist
python3 tools/generate_index.py --packages-root packages --assets-dir dist --updated-at <timestamp> --output index.json
```

Use the sibling AfterNight test binary when you need to verify client-side Extension Manager behavior after building it:

```bash
cd ../afternight
make -C build/make-linux/tests -j4 Test_ProcessFramework
LD_LIBRARY_PATH=bin/clang/release ./bin/clang/release/Test_ProcessFramework --gtest_filter='ExtensionManagerTest.PackageValidatorAcceptsBundledReferenceExtensions:ExtensionManagerTest.FirstPartyMigratedPackagesValidateAndStageThroughFixtureFeed'
```

## Editing Guidance

- Keep package diffs scoped to the package being changed.
- Preserve licenses and notices when moving first-party package sources from `../afternight/extensions/`.
- Do not vendor secrets, tokens, private URLs, local absolute paths, generated caches, or virtual environments.
- Do not rewrite generated package archives by hand.
- Prefer deterministic packaging: sorted entries, stable metadata, pinned hashes.
- Use ASCII by default.
- When an extension needs a new native AfterNight control, add it to the sibling app as a generic reusable control. Do not use extension- or process-specific names for app-side classes, ParamDef types, object names, files, or helpers; keep process-specific wording in the extension schema/configuration.

## Definition Of Done

A package/repository change is ready when:

- manifests validate
- package tests pass
- generated index metadata is updated or confirmed unchanged
- release assets, if produced, hash-match the index
- dependency locks are hashed, and bundled artifacts are target-specific where needed
- license and third-party notices are present
- docs are updated for any new package or process
