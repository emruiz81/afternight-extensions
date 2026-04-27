# Package Format

AfterNight Phase 6 packages are distributed as zstd-compressed tar archives (`.tar.zst`) referenced by the repository `index.json`.

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

The package root may include `requirements.lock`, `wheelhouse/`, `assets/`, helper binaries, or tests when appropriate. CI should build deterministic uncompressed tar payloads with sorted entries, then compress them with zstd for publication.

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
- `package_format_version`
- `protocol_version`
- `sdk_version`

For v1, `package_format_version`, `protocol_version`, and `sdk_version` are integers and currently must be `1`.

## Runtime Targets

Use `runtime_targets` when the package ships target-specific artifacts.

Current target IDs:

- `linux-clang-x86_64`
- `windows-msvc-x86_64`
- `windows-msys2-x86_64`

Pure Python packages may omit `runtime_targets` or publish one asset that supports multiple targets.

## Dependency Metadata

When `requirements_file` is present:

- the file must exist inside the package root
- `dependencies.pip.require_hashes` must be `true`
- package-local `dependencies.pip.find_links` paths must exist inside the package root

Compiled wheels should live under package-local wheel sources such as `wheelhouse/`.

## Safe Extraction Policy

AfterNight decompresses `.tar.zst` assets with libzstd and then applies the same tar extraction policy. Archives are rejected if they contain:

- absolute paths
- `..` path traversal
- symlinks or hard links
- device files, FIFOs, or unsupported special files
- duplicate entries
- excessive path depth, file count, or uncompressed size

The installer writes `extension_package_receipt.json` after successful installation. Do not ship that receipt in package source.
