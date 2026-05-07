# Contributing

Thanks for helping improve the AfterNight extension ecosystem.

This repository is curated. Pull requests are reviewed for package behavior,
source quality, license compatibility, reproducibility, and runtime safety
before an extension can appear in the official Extension Manager index.

## Before You Start

Choose the right reference before editing:

- [docs/README.md](docs/README.md) for the documentation map
- [packages/README.md](packages/README.md) for package folder layout
- [docs/PACKAGE_FORMAT.md](docs/PACKAGE_FORMAT.md) for required manifest and
  release metadata fields
- [docs/HOST_MODES_AND_LICENSING.md](docs/HOST_MODES_AND_LICENSING.md) for
  `sdk_backend`, allowed imports, and host-mode rules
- [docs/LICENSING.md](docs/LICENSING.md) for license, notice, and provenance
  expectations
- [docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md) for validation and release
  workflow

## Package Contribution Checklist

1. Create or update `packages/<extension_id>/package/`.
2. Add or update `extension.json`, Python source, assets, tests, and the
   package README.
3. Choose `sdk_backend` using
   [docs/HOST_MODES_AND_LICENSING.md](docs/HOST_MODES_AND_LICENSING.md) before
   finalizing package license terms.
4. Add a package-local `LICENSE`.
5. Add `THIRD_PARTY_NOTICES.md` when the package includes dependencies, copied
   upstream code, models, helper tools, or binaries.
6. Add provenance metadata and upstream notes when the package is a derived
   work or port.
7. Add or update `packages/<extension_id>/repository.json` with release
   metadata.
8. Use official PyPI indexes plus hash-locked requirements for dependencies
   available from PyPI; do not redistribute those wheels in package assets.
9. Add target-specific packaging metadata under
   `packages/<extension_id>/packaging/` when extension-specific or private
   wheels, custom `.pyd` or `.so` modules, or helper binaries are needed.
10. Run local validation.
11. Open a pull request with a short summary of user-visible behavior, target
    platforms, dependency behavior, bundled artifacts, and license or
    provenance details.

Do not commit built package archives, generated sidecars, wheel downloads,
virtual environments, or caches.

## Updating An Existing Package

- Preserve the extension `id`.
- Bump `version` using SemVer when publishing user-visible changes.
- Keep `repository.json.latest_version` in sync with the newest published
  release.
- Document user-visible changes in the package README or release notes.
- Preserve user settings compatibility unless a migration is explicitly
  documented.
- Refresh dependency locks when dependencies change.
- Add or update `packages/<extension_id>/tests/requirements.txt` when
  package-local tests need Python dependencies that are not part of the base CI
  environment.

## Local Validation

Run repository tooling tests:

```bash
python3 -m unittest discover -s tests
```

Build a package asset:

```bash
python3 tools/build_package.py packages/<extension_id>/package --output-dir dist
```

Regenerate and check the repository index when a published package changes:

```bash
python3 tools/build_repository_assets.py --output-dir dist
python3 tools/generate_index.py \
  --packages-root packages \
  --assets-dir dist \
  --updated-at "$(python3 -c 'import json; print(json.load(open("index.json", encoding="utf-8"))["updated_at"])')" \
  --output /tmp/index.json
diff -u index.json /tmp/index.json
```

Use [docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md) for the full validation,
CI, and maintainer publication workflow.

## Review Expectations

Every official package should have:

- a named maintainer
- clear license metadata
- package validation coverage
- deterministic dependency metadata
- no secrets, tokens, or local machine paths
- no unreviewed network behavior during import or discovery

Packages remain source-staged with `"publish": false` until release assets,
license and notice review, and validation are complete.

## Repository-Level Contributions

Repository tooling, documentation, tests, CI configuration, and non-package
templates are accepted under Apache-2.0 unless the file declares different
terms. Package-level terms live in each package's `extension.json`,
package-local `LICENSE`, and `THIRD_PARTY_NOTICES.md`.

Derived works must keep upstream attribution and provenance visible.

## Related Docs

- [README.md](README.md)
- [docs/README.md](docs/README.md)
- [packages/README.md](packages/README.md)
- [docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md)
