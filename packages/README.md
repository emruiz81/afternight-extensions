# Packages

Each package lives under `packages/<extension_id>/`.

Recommended layout:

```text
packages/<extension_id>/
  package/
    extension.json
    <entry_point>.py
    requirements.lock
    wheelhouse/   # only for custom/private artifacts unavailable from official PyPI
    LICENSE
    THIRD_PARTY_NOTICES.md
  README.md
  tests/
  packaging/
  repository.json
```

The `package/` directory is the source for release archives. CI should build `.tar.zst` assets from this directory and publish them as release assets. Use target-specific assets only when the package bundles extension-specific native artifacts.

New packages should install public Python dependencies from official PyPI using hash-locked requirements and explicit index URLs. Do not publish public PyPI wheels inside package assets; reserve `wheelhouse/` for custom/private binaries or native data that cannot be downloaded from official package repositories.

Use `"publish": false` in `repository.json` when a package is source-staged but not ready for the generated public index.

Keep package IDs stable. Use lowercase snake-case or dotted identifiers that pass AfterNight manifest validation.
