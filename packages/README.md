# Packages

Each package lives under `packages/<extension_id>/`.

Recommended layout:

```text
packages/<extension_id>/
  package/
    extension.json
    <entry_point>.py
    requirements.lock
    wheelhouse/
    LICENSE
    THIRD_PARTY_NOTICES.md
  README.md
  tests/
  packaging/
```

The `package/` directory is the source for release archives. CI should build target-specific `.tar` assets from this directory and publish them as release assets.

Keep package IDs stable. Use lowercase snake-case or dotted identifiers that pass AfterNight manifest validation.
