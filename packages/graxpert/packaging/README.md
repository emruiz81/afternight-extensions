# GraXpert Packaging

GraXpert assets are target-specific because the generated wheelhouse contains compiled wheels and GPU runtime packages.

The source repository keeps:

- `package/graxpert_extension.py`
- `package/extension.json`
- `package/requirements.lock`
- `packaging/prepare_wheelhouse.py`
- `packaging/build_assets.py`

It does not keep generated `.whl` files in git.

Local build from an existing wheelhouse:

```bash
python3 packages/graxpert/packaging/build_assets.py \
  --output-dir dist-graxpert-local \
  --target linux-clang-x86_64 \
  --source-wheelhouse ../afternight/extensions/graxpert/wheelhouse \
  --source-lockfile ../afternight/extensions/graxpert/requirements.lock
```

CI/release-style build:

```bash
python3 packages/graxpert/packaging/build_assets.py \
  --output-dir dist-graxpert \
  --download-wheelhouse
```
