# VeraLux Suite Packaging

This package is not published yet. `PUBLICATION_READINESS.md` is the release
gate for this package and currently keeps the suite source-staged until
representative real-image visual QA is signed off.

When it is ready for release:

1. Confirm the suite-level dependency set and update `package/requirements.lock`
   as additional VeraLux processes are added.
2. Provision the package runtime dependencies for local testing. A clean Python
   needs the host-provided scientific runtime packages such as `numpy` plus the
   packages declared in `package/requirements.lock`.
3. Run the package tests.
4. Complete the `PUBLICATION_READINESS.md` checklist.
5. Build deterministic assets with `tools/build_package.py`.
6. Regenerate the repository index with `tools/generate_index.py`.
7. Remove `publish: false` from `repository.json` only after release assets are
   available, hash-verified, and the visual QA signoff is recorded.
