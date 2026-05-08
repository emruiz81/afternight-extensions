# AfterNight Copilot Review Instructions

Review for defects, regressions, policy violations, missing companion changes,
and unsafe host-process behavior. Treat `docs/` as canonical when guidance
conflicts; use `AGENTS.md` as the working summary.

Primary references:

- `docs/HOST_MODES_AND_LICENSING.md`: `sdk_backend`, allowed imports, host
  process behavior, and license constraints.
- `docs/PACKAGE_FORMAT.md`: archive layout, manifest schema, dependency
  metadata, `repository.json`, and extraction policy.
- `docs/REPOSITORY_POLICY.md`: generated index, signatures, staging, binary
  policy, and notices.
- `docs/RELEASE_PROCESS.md` and `.github/workflows/README.md`: CI, preview,
  and publication workflow behavior.

## Security And Host Safety

Extension code runs inside an AfterNight host process with the same permissions
as the app. Treat filenames, paths, archive contents, package metadata,
settings, view metadata, model files, downloaded assets, environment variables,
and subprocess arguments as untrusted.

Flag concrete paths to code execution, shell execution, unsafe deserialization,
unsafe binary/native-module loading, unsafe archive extraction, or arbitrary
file-system writes. Look especially for `eval`, `exec`, `compile`, unsafe
dynamic imports, `subprocess` with `shell=True`, concatenated shell command
strings, temp/user-writable launch paths, and downloads or unpacking without
source, hash, normalized-path, and file-type validation.

## Host-Mode Compliance

- `sdk_backend` must match imports and capabilities.
- `runtime` packages may use `_afternight_runtime`, Engine-backed `afternight`
  modules, and native `afternight.ui`, but must remain GPL-3.0-family.
- `protocol` packages must not import `_afternight_runtime`, Engine-backed
  modules, native `afternight.ui`, ParamDef-rendered process windows, or C++
  SDK types. They should use `afternight.lite` and `afternight.ui_protocol`.
- `rpc` is reserved and not publishable yet.
- Packages never choose host executable paths directly; the app maps
  `sdk_backend` to the host process.

## Packaging Integrity

- Do not hand-edit generated `index.json` entries. Source metadata, built
  assets, sidecars, and generated index data must stay in sync.
- Keep `extension.json.version` and `repository.json.latest_version` synced for
  published changes.
- `signature_state: "verified"` must come from generated signing sidecars, not
  hand-authored repository metadata.
- When `requirements_file` is present, require exact pins, hashes, and
  `dependencies.pip.require_hashes: true`.
- Do not bundle public PyPI wheels; only extension-specific/private artifacts
  unavailable from official indexes may be bundled.
- New publishable packages must update the static `package_id` dropdown in
  `.github/workflows/publish-release.yml`.

## Docs, License, Provenance

- `LICENSE` must match the manifest license.
- `THIRD_PARTY_NOTICES.md` is required for dependencies, copied source, helper
  binaries, models, or bundled artifacts.
- VeraLux-derived content must keep its provenance fields plus package-local
  `UPSTREAM.md` and `UPSTREAM.json`.
- Flag behavior, release, packaging, or maintainer workflow changes without
  necessary docs or tests.

## Review Style

Prioritize correctness, safety, compatibility, determinism, and missing
companion changes over style. Prefer actionable findings with local evidence
and impact. Skip stylistic comments unless they hide a real defect, validation
gap, or documentation gap. Remember that `validate.yml` rebuilds published
assets, runs Ruff format/lint, runs repository tooling tests, and verifies the
generated candidate index; package-local tests needing `../afternight` are still
expected locally when package behavior changes.
