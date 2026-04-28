# GraXpert Packaging

GraXpert's official release asset is intentionally thin. It contains only the
AfterNight adapter, manifest, license/notice files, and a hash-locked
`requirements.lock`. Public GraXpert and dependency wheels are downloaded from
official PyPI by the host during install.

The source repository keeps:

- `package/graxpert_extension.py`
- `package/extension.json`
- `package/requirements.lock`
- `packaging/refresh_requirements_lock.py`

It does not keep generated `.whl` files in git and official assets do not
redistribute public PyPI wheels.

Official thin asset build:

```bash
python3 tools/build_package.py packages/graxpert/package \
  --output-dir dist-graxpert
```

Lock refresh / compatibility check:

```bash
python3 packages/graxpert/packaging/refresh_requirements_lock.py \
  --target linux-clang-x86_64 \
  --target windows-msvc-x86_64 \
  --download-dir /tmp/graxpert-wheel-check \
  --clean
```
