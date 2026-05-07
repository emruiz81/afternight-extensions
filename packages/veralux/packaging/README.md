# VeraLux Suite Packaging

This package is not published yet. `PUBLICATION_READINESS.md` is the release
gate for this package and currently keeps the suite source-staged until
representative real-image visual QA is signed off.

When it is ready for release:

1. Confirm the suite-level dependency set and update `package/requirements.lock`
   as additional VeraLux processes are added.
2. Run the package tests.
3. Complete the `PUBLICATION_READINESS.md` checklist.
4. Build deterministic assets with `tools/build_package.py`.
5. Regenerate the repository index with `tools/generate_index.py`.
6. Remove `publish: false` from `repository.json` only after release assets are
   available, hash-verified, and the visual QA signoff is recorded.
