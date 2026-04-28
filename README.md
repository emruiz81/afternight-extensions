# AfterNight Extensions

Official extension repository for AfterNight.

This repository hosts curated extension package sources, package metadata, validation tooling, release packaging workflows, and the generated `index.json` consumed by AfterNight's Extension Manager.

## Status

This repository is being initialized for AfterNight Phase 6. The current goal is to make first-party packages such as Cosmic Clarity and GraXpert installable through the official Extension Manager flow while keeping the package format reproducible and reviewable.

Initial Phase 6 is official-repository-only. User-configured third-party repositories, external trust prompts, and third-party repository badges are deferred to a later milestone.

## Repository Layout

```text
.
├── index.json                 # generated/published repository index
├── packages/                  # one folder per extension package
│   └── <extension_id>/
│       ├── package/           # archive root source
│       │   ├── extension.json
│       │   ├── *.py
│       │   ├── requirements.lock
│       │   ├── wheelhouse/       # only for custom/private artifacts unavailable from PyPI
│       │   ├── LICENSE
│       │   └── THIRD_PARTY_NOTICES.md
│       ├── README.md
│       ├── tests/
│       └── packaging/
├── docs/                      # package format and repository policy docs
├── tools/                     # validators, package builders, index generation
└── .github/workflows/         # CI validation and publication workflows
```

Package source belongs in `packages/<extension_id>/package/`. Built archives should normally be produced by CI and published as release assets, not committed directly to `main`. New extensions must not redistribute binary wheels that can be downloaded from the official PyPI index; use hash-locked `requirements.lock` files plus explicit `pip.index_urls` instead.

Release-only metadata belongs in `packages/<extension_id>/repository.json`. The global `index.json` is generated from `extension.json`, `repository.json`, and built asset sidecars.

## Package Format

AfterNight Phase 6 package assets are zstd-compressed tar archives (`.tar.zst`). Each archive extracts to exactly one package root containing `extension.json`. Assets are target-specific only when they bundle extension-specific native artifacts.

Example release asset:

```text
example_extension-1.0.0-all.tar.zst
└── example_extension/
    ├── extension.json
    ├── example_extension.py
    ├── requirements.lock
    ├── LICENSE
    └── THIRD_PARTY_NOTICES.md
```

The repository `index.json` points AfterNight at immutable release assets and provides the authoritative SHA-256 `package_hash` for each downloadable compressed archive.

## Platform Artifacts

Pure Python packages and packages whose dependencies are downloaded from official PyPI may publish one archive for multiple runtime targets.

Packages that bundle extension-specific native helper binaries, private wheels, custom `.pyd`/`.so` modules, models, or platform-specific libraries should publish separate release assets per runtime target when needed, for example:

- `linux-clang-x86_64`
- `windows-msvc-x86_64`

Each target archive should include only the extension-specific artifacts needed for that target. Public PyPI wheels must stay out of package assets and be downloaded by the host from hash-locked requirements during install.

## Contributor Flow

1. Add or update package source under `packages/<extension_id>/package/`.
2. Include `extension.json`, package source, tests, `LICENSE`, and `THIRD_PARTY_NOTICES.md`.
3. Add `packages/<extension_id>/repository.json` with release metadata.
4. Declare dependencies using a hashed `requirements.lock` and official PyPI indexes by default. Use package-local `wheelhouse/` only for custom/private artifacts unavailable from official indexes.
5. Build package assets with `tools/build_repository_assets.py` or a package-specific builder under `packages/<extension_id>/packaging/`.
6. Regenerate `index.json` with `tools/generate_index.py`.
7. Run package validation and tests.
8. Open a pull request.
9. CI validates package layout, manifest metadata, runtime targets, dependency locks, license files, compressed asset hashes, and generated index metadata.
10. Maintainers review code quality, license compatibility, package ownership, and runtime behavior.
11. On release, CI publishes target `.tar.zst` archives and regenerates `index.json`.

Every community package must have a named maintainer. Packages may use their own licenses, but licenses must be compatible with AfterNight's extension distribution policy.

## Trust Policy

Initial official packages may be unsigned if they are served from this official repository and hash-verified before extraction.

Rules for Phase 6:

- every release asset must declare a SHA-256 `package_hash` in `index.json`
- unsigned official packages use `signature_state: "unsigned"`
- `signature_state: "verified"` is reserved until real signing keys and verification are implemented
- `signature_state: "failed"` blocks installation
- `signature_state: "unknown"` should not be emitted by official repository CI

## Related Repository

AfterNight application and SDK source live in the main repository:

```text
https://github.com/emruiz81/afternight
```

During Phase 6, this repository and the main AfterNight repository evolve together: this repo provides package/index artifacts, while the app repo implements the Extension Manager client and install flow.
