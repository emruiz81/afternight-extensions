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

## Build GraXpert Assets

GraXpert publishes large target-specific wheelhouse assets. To reuse an existing local wheelhouse:

```bash
python3 packages/graxpert/packaging/build_assets.py \
  --output-dir dist-graxpert-local \
  --target linux-clang-x86_64 \
  --source-wheelhouse ../afternight/extensions/graxpert/wheelhouse \
  --source-lockfile ../afternight/extensions/graxpert/requirements.lock
```

To resolve the wheelhouse from package metadata instead:

```bash
python3 packages/graxpert/packaging/build_assets.py \
  --output-dir dist-graxpert-local \
  --target linux-clang-x86_64 \
  --download-wheelhouse
```

When no source wheelhouse is supplied, the GraXpert builder resolves the wheelhouse from package metadata. The manual `Build Package Assets` GitHub Actions workflow also uses that download path and uploads generated assets as workflow artifacts.

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
