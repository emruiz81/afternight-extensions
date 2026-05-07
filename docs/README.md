# Documentation Guide

This folder contains the normative package-author and maintainer documentation
for the AfterNight extensions repository. Use this page to choose the right
document before changing package source, release metadata, or publication
policy.

## Reading Paths

| If you need to... | Read first | Then read |
| --- | --- | --- |
| Add or update a package | [PACKAGE_FORMAT.md](PACKAGE_FORMAT.md) | [HOST_MODES_AND_LICENSING.md](HOST_MODES_AND_LICENSING.md), [LICENSING.md](LICENSING.md), [RELEASE_PROCESS.md](RELEASE_PROCESS.md) |
| Choose `sdk_backend` or review allowed imports | [HOST_MODES_AND_LICENSING.md](HOST_MODES_AND_LICENSING.md) | [LICENSING.md](LICENSING.md) |
| Check what can be committed, indexed, or published | [REPOSITORY_POLICY.md](REPOSITORY_POLICY.md) | [RELEASE_PROCESS.md](RELEASE_PROCESS.md) |
| Port a third-party suite or multi-process package | [VERALUX_PORTING_CASE_STUDY.md](VERALUX_PORTING_CASE_STUDY.md) | [PACKAGE_FORMAT.md](PACKAGE_FORMAT.md), [LICENSING.md](LICENSING.md) |

## Contributor Quickstart

1. Choose `sdk_backend` in [HOST_MODES_AND_LICENSING.md](HOST_MODES_AND_LICENSING.md).
2. Lay out the package files using [../packages/README.md](../packages/README.md)
   and fill the required manifest fields in [PACKAGE_FORMAT.md](PACKAGE_FORMAT.md).
3. Add `LICENSE`, `THIRD_PARTY_NOTICES.md`, and provenance metadata when
   required by [LICENSING.md](LICENSING.md).
4. Add or update tests under `packages/<extension_id>/tests/`.
5. Run the local validation flow in [RELEASE_PROCESS.md](RELEASE_PROCESS.md).
6. Regenerate `index.json` when a published package changes.
7. Use [REPOSITORY_POLICY.md](REPOSITORY_POLICY.md) as the final check before
   opening a PR.

## Glossary

- `package root`: the contents of `packages/<extension_id>/package/`, which
  becomes the archive root during publication.
- `repository metadata`: package release metadata in `repository.json` plus the
  built asset sidecars used to generate `index.json`.
- `runtime`: the full hosted backend for GPL-3.0-family packages that use the
  AfterNight Engine or native controls.
- `protocol`: the lite hosted backend for packages that avoid Engine/native UI
  linkage and own their UI or processing.
- `rpc`: a reserved future lite-hosted backend for Engine SDK access through a
  sidecar once AfterNight ships RPC support.

## Document Roles

- [PACKAGE_FORMAT.md](PACKAGE_FORMAT.md): archive layout, manifest fields,
  dependency metadata, runtime targets, and safe extraction rules.
- [HOST_MODES_AND_LICENSING.md](HOST_MODES_AND_LICENSING.md): canonical source
  for `sdk_backend` selection, allowed imports, and host-mode licensing rules.
- [LICENSING.md](LICENSING.md): repository-level versus package-level licensing,
  notices, provenance expectations, and publication blockers.
- [RELEASE_PROCESS.md](RELEASE_PROCESS.md): contributor workflow, validation,
  CI behavior, release tags, and maintainer publication.
- [REPOSITORY_POLICY.md](REPOSITORY_POLICY.md): repository-wide policy for
  `index.json`, signatures, staging, and binary distribution.
- [VERALUX_PORTING_CASE_STUDY.md](VERALUX_PORTING_CASE_STUDY.md): reference
  example for a multi-process upstream suite port.