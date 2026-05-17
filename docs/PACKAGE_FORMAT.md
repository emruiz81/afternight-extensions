# Package Format

This document defines the archive shape, manifest schema, and repository
metadata required for repository-ready AfterNight extension packages. For
workflow and publication steps, see [RELEASE_PROCESS.md](RELEASE_PROCESS.md).
For host selection and allowed imports, see
[HOST_MODES_AND_LICENSING.md](HOST_MODES_AND_LICENSING.md).

## Archive Layout

AfterNight extension packages are distributed as zstd-compressed tar archives
(`.tar.zst`) referenced by the repository `index.json`.

The archive must contain exactly one extension package root:

```text
example_extension-1.0.0-linux-clang-x86_64.tar.zst
└── example_extension/
    ├── extension.json
    ├── example_extension.py
    ├── LICENSE
    └── THIRD_PARTY_NOTICES.md
```

The package root may include `requirements.lock`, `wheelhouse/`, `assets/`,
helper binaries, or tests when appropriate.

## Common Optional Entries

| Path inside package root | Use when |
| --- | --- |
| `requirements.lock` | Python dependencies are declared and must be hash-locked |
| `assets/` | The package needs packaged data files, models, or static resources |
| `wheelhouse/` | The package must ship extension-specific or private artifacts unavailable from official package indexes |
| helper binaries or shared libraries | The extension includes target-specific executables or native modules |
| `UPSTREAM.md` and `UPSTREAM.json` | The package is a documented derived work or port |

Package-local `wheelhouse/` directories are reserved for extension-specific or
private artifacts that are unavailable from official package indexes; do not use
them to redistribute wheels that can be downloaded from PyPI. CI should build
deterministic uncompressed tar payloads with sorted entries, then compress them
with zstd for publication. The repository builder uses POSIX PAX tar headers so
long filenames can be represented without renaming upstream artifacts.

The repository builder writes a sidecar next to each asset:

```text
dist/example_extension-1.0.0-linux-clang-x86_64.tar.zst.metadata.json
```

That sidecar is generated metadata, not package source. It records the
compressed asset hash, size, version, and runtime targets used by
`tools/generate_index.py`.

## Manifest Requirements

Repository-ready packages must declare these `extension.json` fields:

| Field | Purpose |
| --- | --- |
| `id` | Stable package identifier |
| `name` | User-facing package name |
| `version` | Package version published in assets and `index.json` |
| `summary` | Short user-facing description |
| `author` | Package author or maintainer attribution |
| `license` | SPDX-style package license metadata |
| `publisher_id` | Publisher identifier shown by the repository and client |
| `type` | Package implementation type, currently Python for official packages |
| `entry_point` | Python module entry point inside the package root |
| `category` | User-facing package category |
| `launch_mode` | Host launch behavior such as `single_image` |
| `sdk_backend` | Host-mode selector used by AfterNight |
| `package_format_version` | Package schema version |
| `protocol_version` | Host protocol version |
| `sdk_version` | Extension SDK version |

For v1, `package_format_version`, `protocol_version`, and `sdk_version` are
integers and currently must be `1`.

> **Common omissions:** missing `publisher_id`, missing `sdk_backend`, missing
> package-local `LICENSE`, missing notices for derived or bundled content, or
> missing `latest_version` in `repository.json`.

## Provenance For Derived Works

Derived works and ports should also declare user-visible provenance fields so
AfterNight can render attribution in the Extension Manager before and after
installation:

- `attribution`
- `original_author`
- `original_project`
- `original_source_url`
- `upstream_commit`

VeraLux-derived packages must include all five fields and package-local
`UPSTREAM.md` and `UPSTREAM.json` files with the captured source hash and
intentional port divergences.

## `sdk_backend` Requirement

Every repository-ready package must declare `sdk_backend` explicitly.

- `runtime` is for GPL-3.0-family packages that use AfterNight Engine or native
  process controls.
- `protocol` is for packages that use only app or view protocol services and own
  their UI or processing.
- `rpc` is reserved for future Engine SDK over RPC and is not publishable until
  AfterNight ships the RPC backend.

See [HOST_MODES_AND_LICENSING.md](HOST_MODES_AND_LICENSING.md) for the canonical
host-mode matrix, allowed imports, and license restrictions.

## Process Capabilities

Each `processes[]` entry may declare a `capabilities` object. Missing fields use
AfterNight defaults. In addition to execution, preview, mask, weight, and source
channel metadata, star-separation processes can advertise reusable output roles:

| Field | Type | Meaning |
| --- | --- | --- |
| `starless_generator` | boolean | The process can generate a starless image usable by other native or extension processes. |
| `star_mask_generator` | boolean | The process can generate an extracted-stars or star-mask image usable by other processes. |

These flags are discovery metadata only. The process is still launched through
its normal `launch_mode`, and availability follows the package environment state
reported by AfterNight.

## Runtime Targets

Use `runtime_targets` when the package ships target-specific artifacts.

Current target IDs:

- `linux-clang-x86_64`
- `windows-msvc-x86_64`

Pure Python packages may omit `runtime_targets` or publish one asset that
supports multiple targets.

## Repository Release Metadata

Each package folder must include release-only metadata outside the archive
source:

```text
packages/example_extension/
├── package/
│   └── extension.json
└── repository.json
```

Example:

```json
{
  "latest_version": "1.0.0",
  "releases": [
    {
      "version": "1.0.0",
      "min_app_version": "2.0.0",
      "changelog": "Initial release.",
      "published_at": "2026-04-27T00:00:00Z",
      "asset_base_url": "https://github.com/emruiz81/afternight-extensions/releases/download/example_extension-v1.0.0",
      "signature_state": "unsigned",
      "signature_detail": "Unsigned official package; SHA-256 verified from index."
    }
  ]
}
```

`repository.json` is merged with `extension.json` and built asset sidecars to
generate the candidate `index.json`. The generated client index is built from
the current package source and should describe the current publishable release
for that package. Older package archives remain available as GitHub Releases,
but they are not rebuilt from newer source trees or carried forward in the
generated index unless future tooling explicitly learns how to preserve external
historical asset metadata.

Set `"publish": false` in `repository.json` for source-staged packages that
should validate locally but remain absent from generated indexes until their
release assets are available. After release assets are uploaded, the maintainer
publish workflow updates the client-facing `live` index.

For non-draft maintainer publication, `tools/sign_repository_assets.py` signs
the built asset sidecar and `tools/generate_index.py` emits verified asset
metadata from that sidecar:

```json
{
  "name": "example_extension-1.0.0-all.tar.zst",
  "download_url": "https://github.com/emruiz81/afternight-extensions/releases/download/example_extension-v1.0.0/example_extension-1.0.0-all.tar.zst",
  "package_hash": "sha256:...",
  "signature_state": "verified",
  "signature_detail": "Verified official AfterNight package signature (Ed25519 key afternight-official-ed25519-2026-05).",
  "signature_algorithm": "ed25519",
  "signature_key_id": "afternight-official-ed25519-2026-05",
  "signature": "base64-ed25519-detached-signature",
  "runtime_targets": ["linux-clang-x86_64", "windows-msvc-x86_64"]
}
```

The detached Ed25519 signature covers this canonical UTF-8 payload:

```text
afternight-extension-asset-signature-v1
package_id=<extension id>
version=<release version>
asset_name=<asset filename>
package_hash=sha256:<lowercase hex>
runtime_targets=<comma-joined sorted runtime targets>
signature_algorithm=ed25519
signature_key_id=<key id>
```

`package_hash` remains mandatory and is checked before extraction. Do not set
`signature_state: "verified"` in `repository.json`; verified signatures are
generated only by the signing tool from release sidecars.

## Dependency Metadata

When `requirements_file` is present:

- the file must exist inside the package root
- `dependencies.pip.require_hashes` must be `true`
- every requirement line must be exactly pinned with `==` and include at least
  one `--hash=sha256:` value
- public PyPI dependencies should use explicit
  `dependencies.pip.index_urls` or `extra_index_urls` and fully pinned hashes
- package-local `dependencies.pip.find_links` paths must exist inside the
  package root and are only for extension-specific or private artifacts
  unavailable from official indexes

Packages that declare dependencies must include `THIRD_PARTY_NOTICES.md`.

Compiled wheels from official PyPI should be downloaded by the host during
install, not bundled into release assets. Bundle only extension-specific
binaries such as custom `.pyd` or `.so` modules, helper executables, private
wheels, or native data that cannot be fetched from official package repositories.

## Safe Extraction Policy

AfterNight decompresses `.tar.zst` assets with libzstd and then applies the
same tar extraction policy. Archives are rejected if they contain:

- absolute paths
- `..` path traversal
- symlinks or hard links
- device files, FIFOs, or unsupported special files
- duplicate entries
- excessive path depth, file count, or uncompressed size

The installer writes `extension_package_receipt.json` after successful
installation. Do not ship that receipt in package source.

## Related Docs

- [README.md](README.md)
- [HOST_MODES_AND_LICENSING.md](HOST_MODES_AND_LICENSING.md)
- [LICENSING.md](LICENSING.md)
- [RELEASE_PROCESS.md](RELEASE_PROCESS.md)
