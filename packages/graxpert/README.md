# GraXpert AI

GraXpert AI exposes GraXpert background extraction, denoise, and deconvolution inside AfterNight through the Python extension runtime.

This directory stores source and packaging metadata only. Official release assets are thin: they contain the AfterNight adapter, manifest, and hash-locked requirements file, while GraXpert and public dependency wheels are downloaded from official PyPI during host-managed install.

## Processes

- GraXpert AI Background Extraction
- GraXpert AI Denoise
- GraXpert AI Deconvolution

## Runtime Targets

Supported targets:

- `linux-clang-x86_64`
- `windows-msvc-x86_64`

## Packaging

Use `tools/build_package.py` to build the thin official release asset. `packaging/refresh_requirements_lock.py` is only a lock-maintenance helper for verifying target wheel availability and refreshing hashes; do not publish public PyPI wheels inside official package assets.
