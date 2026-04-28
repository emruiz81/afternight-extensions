# GraXpert Packaging

GraXpert's official release asset is intentionally thin. It contains only the
AfterNight adapter, manifest, license/notice files, and a hash-locked
`requirements.lock`. Public GraXpert and dependency wheels are downloaded from
official PyPI by the host during install.

The source repository keeps:

- `package/graxpert_extension.py`
- `package/extension.json`
- `package/requirements.lock`
- `packaging/prepare_wheelhouse.py`
- `packaging/build_assets.py`

It does not keep generated `.whl` files in git and official assets do not
redistribute public PyPI wheels.

Official thin asset build:

```bash
python3 packages/graxpert/packaging/build_assets.py \
  --output-dir dist-graxpert
```

Lock refresh / compatibility check:

```bash
python3 packages/graxpert/packaging/prepare_wheelhouse.py \
  --target linux-clang-x86_64 \
  --target windows-msvc-x86_64 \
  --wheelhouse /tmp/graxpert-wheel-check \
  --lockfile packages/graxpert/package/requirements.lock \
  --clean
```

Package-local wheelhouse builds remain available only for custom/private
extension-specific binaries that are unavailable from official package indexes.
Do not use them to publish wheels that can be fetched from PyPI.
