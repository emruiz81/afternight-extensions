# Licensing

This repository has repository-level licensing plus package-local licensing.
Always review the package-local `LICENSE`, `THIRD_PARTY_NOTICES.md`, and
`extension.json` before publishing or redistributing an extension package.

Host-mode licensing rules are defined in
[Host Modes and Licensing](HOST_MODES_AND_LICENSING.md). In short:
`sdk_backend = runtime` packages are full hosted and must use a GPL-3.0-family license;
`sdk_backend = protocol` packages are lite hosted and may use non-GPL licenses
when they avoid AfterNight Engine/native-control imports; `sdk_backend = rpc`
is reserved until the AfterNight RPC backend ships.

## Repository-Level License

Repository tooling, documentation, CI configuration, tests, and non-package
templates are distributed under Apache-2.0 unless a file declares a different
license. The Apache-2.0 license text is available at the repository root in
`LICENSE`.

Package directories are licensed separately. Everything under
`packages/<extension_id>/` is governed by that package's manifest, package-local
`LICENSE`, and notices unless a file inside the package declares a more specific
license. The repository-level Apache-2.0 license does not relicense package-local
GPL code or upstream-derived content.

## Package License Summary

| Package | Published | Package license | Notes |
| --- | --- | --- | --- |
| `cosmic_clarity` | Yes | GPL-3.0 | Contains the AfterNight adapter only. Upstream Cosmic Clarity executables, models, and runtime payloads are not bundled. |
| `graxpert` | Yes | GPL-3.0 | Contains the AfterNight adapter and hash-locked requirements. GraXpert and public dependency wheels are downloaded from PyPI by the host during install. |
| `veralux` | Yes | GPL-3.0-or-later | Derived from Riccardo Paterniti's VeraLux Siril scripts. Provenance is recorded in `UPSTREAM.md`, `UPSTREAM.json`, and `THIRD_PARTY_NOTICES.md`. |

## Publication Requirements

Every publishable package must include:

- SPDX-style license metadata in `extension.json`
- explicit `sdk_backend` metadata in `extension.json`
- a package-local `LICENSE` file
- `THIRD_PARTY_NOTICES.md` when dependencies, copied source, models, helper
  binaries, generated artifacts, or upstream-derived code are included
- provenance fields for derived works when the source project, author, commit, or
  source URL should be visible to users

Packages using `sdk_backend = runtime` must use a GPL-3.0-family license
(`GPL-3.0`, `GPL-3.0-only`, or `GPL-3.0-or-later`).
Packages using `sdk_backend = protocol` may use non-GPL licenses if they do not
import `_afternight_runtime`, Engine-backed `afternight` modules, or native
AfterNight controls. Packages using `sdk_backend = rpc` are blocked until the
target AfterNight release ships RPC support and the package passes the same
non-linking review.

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
- a non-GPL package declares `sdk_backend = runtime`
- a lite-hosted package imports `_afternight_runtime`, Engine-backed `afternight`
  modules, or native AfterNight controls
- a package declares `sdk_backend = rpc` before the target AfterNight release
  supports RPC extension hosting

## References

- Apache License 2.0: https://www.apache.org/licenses/LICENSE-2.0
- GNU license list and GPL compatibility notes: https://www.gnu.org/licenses/license-list.html#apache2
