# Tools

Repository-local tools live here.

## Requirements

The package builder uses the system `zstd` executable. On Linux:

```bash
sudo apt-get install zstd
```

## Build A Package

```bash
python3 tools/build_package.py packages/<extension_id>/package --output-dir dist
```

The builder creates:

- `dist/<extension_id>-<version>-<target>.tar.zst`
- `dist/<extension_id>-<version>-<target>.tar.zst.metadata.json`

The archive is deterministic: entries are sorted, tar metadata is stable, symlinks and special files are rejected, and the sidecar hash is calculated from the compressed `.tar.zst` asset.

For target-specific packages, repeat `--runtime-target`:

```bash
python3 tools/build_package.py packages/<extension_id>/package \
  --output-dir dist \
  --runtime-target linux-clang-x86_64
```

To build all currently published packages for the generated repository index:

```bash
python3 tools/build_repository_assets.py --output-dir dist
```

Packages with `"publish": false` in `packages/<extension_id>/repository.json` are source-staged but omitted from repository asset builds and `index.json`.

The package validator enforces host-mode policy from
`docs/HOST_MODES_AND_LICENSING.md`:

- every manifest must declare `sdk_backend`
- `runtime` packages must use a GPL-3.0-family package license
- `protocol` packages must not import `_afternight_runtime` or Engine-backed
  `afternight` modules
- `rpc` packages are rejected until the target AfterNight release ships RPC
  extension hosting

## Build GraXpert Assets

GraXpert's official asset is thin and PyPI-backed:

```bash
python3 tools/build_package.py packages/graxpert/package \
  --output-dir dist-graxpert
```

Refresh the hash lock only when changing GraXpert dependencies:

```bash
python3 packages/graxpert/packaging/refresh_requirements_lock.py \
  --target linux-clang-x86_64 \
  --target windows-msvc-x86_64 \
  --download-dir /tmp/graxpert-wheel-check \
  --clean
```

New extensions must not redistribute public PyPI wheels inside package assets; use explicit indexes plus hash-locked requirements instead.

## Check VeraLux Upstream Provenance

VeraLux ports keep a machine-readable source baseline in
`packages/veralux/package/UPSTREAM.json`. To verify the pinned hashes, source
versions, and file-specific commits against a local `siril-scripts` checkout:

```bash
python3 tools/check_veralux_upstream.py \
  --upstream-checkout /path/to/siril-scripts
```

To review what changed in a newer upstream checkout before rebasing the local
ports, inspect another ref:

```bash
python3 tools/check_veralux_upstream.py \
  --upstream-checkout /path/to/siril-scripts \
  --ref HEAD
```

The command exits with `0` when every captured source matches, `2` when a source
differs, and `1` for local tooling or git errors. Use `--json` for machine-readable
output in review scripts.

## Generate The Index

```bash
python3 tools/generate_index.py \
  --packages-root packages \
  --assets-dir dist \
  --updated-at 2026-04-27T00:00:00Z \
  --output index.json
```

Each package must provide `packages/<extension_id>/repository.json` with release-level metadata such as `min_app_version`, changelog text, and publication timestamp.

## Validate Locally

```bash
python3 -m unittest discover -s tests
mkdir -p dist
python3 tools/build_repository_assets.py --output-dir dist
python3 tools/generate_index.py --packages-root packages --assets-dir dist --updated-at "$(python3 -c 'import json; print(json.load(open("index.json"))["updated_at"])')" --output /tmp/index.json
diff -u index.json /tmp/index.json
```
