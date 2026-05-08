---
description: "Use when reviewing package manifests, release metadata, dependency locks, notices, provenance files, or generated index data. Focus on schema compliance, release integrity, licensing, and provenance."
applyTo: "packages/**/package/extension.json,packages/**/repository.json,packages/**/package/requirements.lock,packages/**/package/LICENSE,packages/**/package/THIRD_PARTY_NOTICES.md,packages/**/package/UPSTREAM.md,packages/**/package/UPSTREAM.json,index.json"
---

# Metadata And Packaging Review Focus

- `extension.json` must keep the required manifest fields, and
  `package_format_version`, `protocol_version`, and `sdk_version` must remain
  `1` unless the repository policy changes.
- Keep `extension.json.version` synchronized with
  `repository.json.latest_version` when the published release changes.
- `sdk_backend` and `license` must agree with the host-mode and licensing
  rules in `docs/HOST_MODES_AND_LICENSING.md`.
- `index.json` is generated review metadata. Flag direct/manual edits unless
  the corresponding source metadata, built assets, sidecars, and generated
  output were updated together.
- `signature_state: "verified"` must come from generated signing sidecars.
  `repository.json` must not hand-author verified signatures.
- When dependency metadata uses a `requirements_file`, require exact `==`
  pins, at least one `--hash=sha256:` per requirement, and
  `dependencies.pip.require_hashes: true`.
- Flag attempts to bundle public PyPI wheels or other publicly downloadable
  artifacts that repository policy says should be fetched by the host during
  install instead.
- `THIRD_PARTY_NOTICES.md`, `LICENSE`, and VeraLux provenance files must stay
  complete when dependencies, copied code, helper binaries, models, or derived
  content change.
- Only require `runtime_targets` when target-specific artifacts actually
  justify them.
