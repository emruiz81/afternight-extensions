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
│       │   ├── wheelhouse/
│       │   ├── LICENSE
│       │   └── THIRD_PARTY_NOTICES.md
│       ├── README.md
│       ├── tests/
│       └── packaging/
├── docs/                      # package format and repository policy docs
├── tools/                     # validators, package builders, index generation
└── .github/workflows/         # CI validation and publication workflows
```

Package source belongs in `packages/<extension_id>/package/`. Built archives and heavyweight wheels should normally be produced by CI and published as release assets, not committed directly to `main`.

## Package Format

AfterNight Phase 6 package assets are target-specific zstd-compressed tar archives (`.tar.zst`). Each archive extracts to exactly one package root containing `extension.json`.

Example release asset:

```text
graxpert-1.0.0-linux-clang-x86_64.tar.zst
└── graxpert/
    ├── extension.json
    ├── graxpert_extension.py
    ├── requirements.lock
    ├── wheelhouse/
    ├── LICENSE
    └── THIRD_PARTY_NOTICES.md
```

The repository `index.json` points AfterNight at immutable release assets and provides the authoritative SHA-256 `package_hash` for each downloadable compressed archive.

## Platform Wheels

Pure Python packages may publish one archive for multiple runtime targets.

Packages with compiled wheels, native helper binaries, CUDA/ONNX dependencies, or platform-specific libraries should publish separate release assets per runtime target, for example:

- `linux-clang-x86_64`
- `windows-msvc-x86_64`
- `windows-msys2-x86_64`

Each target archive should include only the wheelhouse and native artifacts needed for that target.

## Contributor Flow

1. Add or update package source under `packages/<extension_id>/package/`.
2. Include `extension.json`, package source, tests, `LICENSE`, and `THIRD_PARTY_NOTICES.md`.
3. Declare dependencies using a hashed `requirements.lock` and package-local `wheelhouse/` when needed.
4. Run package validation and tests.
5. Open a pull request.
6. CI validates package layout, manifest metadata, runtime targets, dependency locks, license files, and generated index metadata.
7. Maintainers review code quality, license compatibility, package ownership, and runtime behavior.
8. On release, CI publishes target `.tar.zst` archives and regenerates `index.json`.

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
