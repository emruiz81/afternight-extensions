# Packages

Each package lives under `packages/<extension_id>/`.

The `package/` directory becomes the root of the published `.tar.zst` archive.
Everything outside `package/` supports authoring, tests, staging, and release
metadata.

## Recommended Layout

```text
packages/<extension_id>/
  package/
    extension.json
    <entry_point>.py
    requirements.lock              # when Python dependencies are declared
    assets/                        # optional package data
    wheelhouse/                    # only for extension-specific/private artifacts
    LICENSE
    THIRD_PARTY_NOTICES.md         # required when bundling deps/models/binaries/copied source
    UPSTREAM.md                    # required for derived packages when applicable
    UPSTREAM.json                  # required for derived packages when applicable
  README.md
  tests/
    requirements.txt               # optional; installed by package-test CI
  packaging/
  repository.json
```

Use target-specific assets only when the package bundles extension-specific
native artifacts. Pure Python packages can usually omit `runtime_targets` or
publish one cross-target asset.

Current runtime target IDs:

- `linux-clang-x86_64`
- `windows-msvc-x86_64`

## Repository-Ready Checklist

Before opening a PR, make sure the package includes:

- `package/extension.json` with these required fields: `id`, `name`,
  `version`, `summary`, `author`, `license`, `publisher_id`, `type`,
  `entry_point`, `category`, `launch_mode`, `sdk_backend`,
  `package_format_version`, `protocol_version`, and `sdk_version`
- `package_format_version`, `protocol_version`, and `sdk_version` set to `1`
- a package-local `LICENSE` that matches `extension.json`
- `THIRD_PARTY_NOTICES.md` when dependencies, models, helper binaries, copied
  upstream source, or bundled artifacts are included
- `repository.json` for release metadata and publication staging
- tests under `tests/`

If the package is a derived work or port, also declare these provenance fields
in `extension.json`:

- `attribution`
- `original_author`
- `original_project`
- `original_source_url`
- `upstream_commit`

VeraLux-derived packages must also include `UPSTREAM.md` and `UPSTREAM.json`.

Keep package IDs stable. Use lowercase snake-case or dotted identifiers that
pass AfterNight manifest validation.

## Dependencies And Bundled Artifacts

Public Python dependencies should come from official PyPI using explicit index
URLs and hash-locked requirements.

- Keep `requirements.lock` inside `package/` when Python dependencies are used.
- When `requirements_file` is present, set
  `dependencies.pip.require_hashes` to `true`.
- Every requirement in a lock file must be exactly pinned with `==` and include
  at least one `--hash=sha256:` value.
- Packages that declare dependencies must include `THIRD_PARTY_NOTICES.md`.
- Do not bundle public PyPI wheels inside package assets.
- Reserve `wheelhouse/` and `dependencies.pip.find_links` for
  extension-specific or private artifacts that are unavailable from official
  package indexes.

Do not commit generated release archives, metadata sidecars, `dist/`, virtual
environments, or caches.

## SDK Backend

Every package must declare `sdk_backend` explicitly:

| `sdk_backend` | Host mode | Use when | License rule |
| --- | --- | --- | --- |
| `runtime` | Full hosted | Package uses AfterNight Engine or native controls | Must be GPL-3.0-family |
| `protocol` | Lite hosted | Package uses only app/view protocol services and owns its UI/processing | Can be non-GPL if it avoids Engine/native-control imports |
| `rpc` | Future lite host plus SDK sidecar | Reserved for future Engine SDK over RPC | Not publishable until AfterNight supports RPC |

`protocol` packages should use `afternight.ui_protocol` instead of the native
`afternight.ui` surface.

See [../docs/HOST_MODES_AND_LICENSING.md](../docs/HOST_MODES_AND_LICENSING.md)
before adding a new package.

## Release Metadata

Each package folder must include `repository.json` next to `package/`. This file
supplies release metadata that is merged into the generated `index.json`.

- Keep `latest_version` in sync with the most recent published release.
- Use `"publish": false` when a package is source-staged but not ready for
  generated indexes.
- Published releases should declare `version`, `min_app_version`, `changelog`,
  `published_at`, `asset_base_url`, `signature_state`, and
  `signature_detail`.
- The generated index is latest-source metadata. For package updates, replace
  the current release metadata with the new version; older archives remain on
  their GitHub Release tags but are not regenerated into `index.json`.
- `index.json` is generated from package manifests, `repository.json`, and
  built asset sidecars. Do not hand-edit package entries in the index.
  The checked-in copy on `main` is a candidate index; the release workflow
  updates the client-facing `live` branch after assets are uploaded.

## Local Validation

`zstd` must be available on `PATH` to build release assets.

Run repository tooling tests:

```bash
python3 -m pip install --require-hashes -r tools/quality/requirements.lock
python3 -m ruff format --check .
python3 -m ruff check .
python3 -m unittest discover -s tests
```

Run package tests after installing any optional test requirements:

```bash
python3 -m unittest discover -s packages/<extension_id>/tests
```

Build the package asset and regenerate the index for validation:

```bash
python3 tools/build_package.py packages/<extension_id>/package --output-dir dist
python3 tools/generate_index.py --packages-root packages --assets-dir dist --updated-at <timestamp> --output index.json
```

See [../docs/PACKAGE_FORMAT.md](../docs/PACKAGE_FORMAT.md) for the canonical
package schema and [../docs/RELEASE_PROCESS.md](../docs/RELEASE_PROCESS.md) for
the PR, CI, and maintainer publication workflow.
