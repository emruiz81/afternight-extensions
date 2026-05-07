# Licensing

This repository has repository-level licensing plus package-local licensing.
Always review the package-local `LICENSE`, `THIRD_PARTY_NOTICES.md`, and
`extension.json` before publishing or redistributing an extension package.

## Repository-Level License

Repository tooling, documentation, CI configuration, tests, and
AfterNight-maintained adapter code are distributed under GPL-3.0 unless a file or
package declares a different license. The GPL-3.0 license text is available at
the repository root in `LICENSE`.

## Package License Summary

| Package | Published | Package license | Notes |
| --- | --- | --- | --- |
| `cosmic_clarity` | Yes | GPL-3.0 | Contains the AfterNight adapter only. Upstream Cosmic Clarity executables, models, and runtime payloads are not bundled. |
| `graxpert` | Yes | GPL-3.0 | Contains the AfterNight adapter and hash-locked requirements. GraXpert and public dependency wheels are downloaded from PyPI by the host during install. |
| `veralux` | No, source-staged | GPL-3.0-or-later | Derived from Riccardo Paterniti's VeraLux Siril scripts. Provenance is recorded in `UPSTREAM.md`, `UPSTREAM.json`, and `THIRD_PARTY_NOTICES.md`. |

## Publication Requirements

Every publishable package must include:

- SPDX-style license metadata in `extension.json`
- a package-local `LICENSE` file
- `THIRD_PARTY_NOTICES.md` when dependencies, copied source, models, helper
  binaries, generated artifacts, or upstream-derived code are included
- provenance fields for derived works when the source project, author, commit, or
  source URL should be visible to users

Public PyPI wheels must not be redistributed in package assets. When a package
depends on public PyPI artifacts, keep a hash-locked `requirements.lock` and let
AfterNight's installer resolve those artifacts from the declared package index.

## Blocking Issues

Do not publish a package when any of these are true:

- license metadata is missing or ambiguous
- third-party notices are missing for bundled or derived content
- package files contain secrets, local absolute paths, private URLs, or tokens
- release assets redistribute public wheels or binaries that should be resolved
  from official package indexes
- upstream license terms are incompatible with official AfterNight extension
  distribution
