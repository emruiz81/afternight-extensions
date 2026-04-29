# VeraLux Suite Packaging

This package is not published yet. When it is ready for release:

1. Confirm the suite-level dependency set and update `package/requirements.lock`
   as additional VeraLux processes are added.
2. Run the package tests.
3. Build deterministic assets with `tools/build_package.py`.
4. Regenerate the repository index with `tools/generate_index.py`.
5. Remove `publish: false` from `repository.json` only after release assets are
   available and hash-verified.
