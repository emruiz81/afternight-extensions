# Contributing

Thanks for helping improve the AfterNight extension ecosystem.

This repository is curated. Pull requests are reviewed for package behavior, source quality, license compatibility, reproducibility, and runtime safety before an extension can appear in the official Extension Manager index.

## Adding A Package

1. Create `packages/<extension_id>/package/`.
2. Add `extension.json`, Python source, assets, tests, and package docs.
3. Add `LICENSE`.
4. Add `THIRD_PARTY_NOTICES.md` if the package includes dependencies, copied upstream code, models, helper tools, or binaries.
5. Add target-specific packaging metadata under `packages/<extension_id>/packaging/` when platform-specific wheels or helper binaries are needed.
6. Run validation.
7. Open a pull request with a short description, target platforms, dependencies, and license summary.

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

Initial Phase 6 accepts only packages distributed from this official repository. Third-party repository support is future work.
