# Contributing

Thanks for helping improve the AfterNight extension ecosystem.

This repository is curated. Pull requests are reviewed for package behavior, source quality, license compatibility, reproducibility, and runtime safety before an extension can appear in the official Extension Manager index.

## Adding A Package

1. Create `packages/<extension_id>/package/`.
2. Add `extension.json`, Python source, assets, tests, and package docs.
3. Add `LICENSE`.
4. Add `THIRD_PARTY_NOTICES.md` if the package includes dependencies, copied upstream code, models, helper tools, or binaries.
5. Add `packages/<extension_id>/repository.json` with release metadata.
6. Use official PyPI indexes plus hash-locked requirements for dependencies available from PyPI; do not redistribute those wheels in package assets.
7. Add target-specific packaging metadata under `packages/<extension_id>/packaging/` when extension-specific/private wheels, custom `.pyd`/`.so` modules, or helper binaries are needed.
8. Run `python3 tools/build_package.py packages/<extension_id>/package --output-dir dist`.
9. Regenerate `index.json` with `tools/generate_index.py`.
10. Run validation.
11. Open a pull request with a short description, target platforms, dependency behavior, bundled artifacts, and license summary.

## Updating A Package

- Preserve the extension `id`.
- Bump `version` using SemVer.
- Document user-visible changes in the package README or release notes.
- Preserve user settings compatibility unless a migration is explicitly documented.
- Refresh dependency locks when dependencies change.

## Review Requirements

Every official package must have:

- a named maintainer
- clear license metadata
- package validation coverage
- deterministic dependency metadata
- no secrets or local machine paths
- no unreviewed network behavior during import or discovery

Packages remain source-staged with `"publish": false` until release assets,
license/notice review, and validation are complete.

## Licensing Expectations

The repository-level license is documented in `LICENSE` and
`docs/LICENSING.md`. Package-level terms live in each package's
`extension.json`, package-local `LICENSE`, and `THIRD_PARTY_NOTICES.md`.

Derived works must keep upstream attribution and provenance visible. Dependency
locks must distinguish between public package-index artifacts that the host
downloads during install and any extension-specific artifacts that are bundled in
the package asset.
