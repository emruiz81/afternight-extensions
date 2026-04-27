# GraXpert Packaging

GraXpert assets are target-specific because the generated wheelhouse contains compiled wheels and GPU runtime packages.

The source repository keeps:

- `package/graxpert_extension.py`
- `package/extension.json`
- `package/requirements.lock`
- `packaging/prepare_wheelhouse.py`
- `packaging/build_assets.py`

It does not keep generated `.whl` files in git.
