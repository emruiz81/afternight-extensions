# Package Format

AfterNight extension packages are distributed as zstd-compressed tar archives (`.tar.zst`) referenced by the repository `index.json`.

## Archive Layout

The archive must contain exactly one extension package root:

```text
example_extension-1.0.0-linux-clang-x86_64.tar.zst
└── example_extension/
    ├── extension.json
    ├── example_extension.py
    ├── LICENSE
    └── THIRD_PARTY_NOTICES.md
```

The package root may include `requirements.lock`, `wheelhouse/`, `assets/`, helper binaries, or tests when appropriate. Package-local `wheelhouse/` directories are reserved for extension-specific/private artifacts that are unavailable from official package indexes; do not use them to redistribute wheels that can be downloaded from PyPI. CI should build deterministic uncompressed tar payloads with sorted entries, then compress them with zstd for publication. The repository builder uses POSIX PAX tar headers so long filenames can be represented without renaming upstream artifacts.

The repository builder writes a sidecar next to each asset:

```text
dist/example_extension-1.0.0-linux-clang-x86_64.tar.zst.metadata.json
```

That sidecar is generated metadata, not package source. It records the compressed asset hash, size, version, and runtime targets used by `tools/generate_index.py`.

## Required Manifest Fields

Repository-ready packages must declare:

- `id`
- `name`
- `version`
- `summary`
- `author`
- `license`
- `publisher_id`
- `type`
- `entry_point`
- `category`
- `launch_mode`
- `sdk_backend`
- `package_format_version`
- `protocol_version`
- `sdk_version`

For v1, `package_format_version`, `protocol_version`, and `sdk_version` are integers and currently must be `1`.

Derived works and ports should also declare user-visible provenance fields so
AfterNight can render attribution in the Extension Manager before and after
installation:

- `attribution`
- `original_author`
- `original_project`
- `original_source_url`
- `upstream_commit`

VeraLux-derived packages must include all five fields and package-local
`UPSTREAM.md` / `UPSTREAM.json` files with the captured source hash and
intentional port divergences.

## Runtime Targets

Use `runtime_targets` when the package ships target-specific artifacts.

Current target IDs:

- `linux-clang-x86_64`
- `windows-msvc-x86_64`

Pure Python packages may omit `runtime_targets` or publish one asset that supports multiple targets.

## Host Mode and SDK Backend

Every repository-ready package must declare `sdk_backend` explicitly. AfterNight
uses this field to choose the host process:

| `sdk_backend` | Host mode | Intended use |
| --- | --- | --- |
| `runtime` | Full hosted | GPL-3.0-family packages that use AfterNight Engine and/or native process controls |
| `protocol` | Lite hosted | Packages that use only app/view protocol services and own their UI/processing |
| `rpc` | Lite hosted + SDK sidecar | Future Engine SDK over RPC; unavailable until AfterNight ships the RPC backend |

Examples:

```json
{
  "license": "GPL-3.0-or-later",
  "launch_mode": "single_image",
  "sdk_backend": "runtime"
}
```

```json
{
  "license": "MIT",
  "launch_mode": "single_image",
  "sdk_backend": "protocol"
}
```

`runtime` packages must use a GPL-3.0-family license. `protocol` packages must not import
`_afternight_runtime`, Engine-backed `afternight` modules, or the native
`afternight.ui` surface. Lite packages should use `afternight.ui_protocol` for
protocol-safe result/dialog/theme helpers. `rpc` packages are rejected until the
target AfterNight release advertises RPC support. See
[Host Modes and Licensing](HOST_MODES_AND_LICENSING.md).

## Repository Release Metadata

Each package folder must include release-only metadata outside the archive source:

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
      "signature_state": "unsigned"
    }
  ]
}
```

`repository.json` is merged with `extension.json` and built asset sidecars to generate `index.json`.

Set `"publish": false` in `repository.json` for source-staged packages that should validate locally but remain absent from the generated public index until their release assets are available.

## Dependency Metadata

When `requirements_file` is present:

- the file must exist inside the package root
- `dependencies.pip.require_hashes` must be `true`
- public PyPI dependencies should use explicit `dependencies.pip.index_urls` / `extra_index_urls` and fully pinned hashes
- package-local `dependencies.pip.find_links` paths must exist inside the package root and are only for extension-specific/private artifacts unavailable from official indexes

Compiled wheels from official PyPI should be downloaded by the host during install, not bundled into release assets. Bundle only extension-specific binaries such as custom `.pyd`/`.so` modules, helper executables, private wheels, or native data that cannot be fetched from official package repositories.

## Safe Extraction Policy

AfterNight decompresses `.tar.zst` assets with libzstd and then applies the same tar extraction policy. Archives are rejected if they contain:

- absolute paths
- `..` path traversal
- symlinks or hard links
- device files, FIFOs, or unsupported special files
- duplicate entries
- excessive path depth, file count, or uncompressed size

The installer writes `extension_package_receipt.json` after successful installation. Do not ship that receipt in package source.
