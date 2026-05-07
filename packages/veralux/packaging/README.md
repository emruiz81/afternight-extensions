# VeraLux Suite Packaging

This package is published through the official AfterNight extension index.
`PUBLICATION_READINESS.md` records the release gates and validation commands for
the current VeraLux release.

For a future VeraLux release:

1. Confirm the suite-level dependency set and update `package/requirements.lock`
   as additional VeraLux processes are added.
2. Provision the package runtime dependencies for local testing. A clean Python
   needs the host-provided scientific runtime packages such as `numpy` plus the
   packages declared in `package/requirements.lock`.
3. Run the package tests.
4. Complete the `PUBLICATION_READINESS.md` checklist.
5. Build deterministic assets with `tools/build_package.py`.
6. Regenerate the repository index with `tools/generate_index.py`.
7. Regenerate `index.json` only after release assets are available and
   hash-verified.
