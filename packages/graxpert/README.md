# GraXpert AI

GraXpert AI exposes GraXpert background extraction, denoise, and deconvolution inside AfterNight through the Python extension runtime.

This directory stores source and packaging metadata only. The generated release assets need a target-specific offline wheelhouse and are intentionally not committed to `main`.

## Processes

- GraXpert AI Background Extraction
- GraXpert AI Denoise
- GraXpert AI Deconvolution

## Runtime Targets

Current staged targets:

- `linux-clang-x86_64`
- `windows-msvc-x86_64`

The Windows MSYS2 target is not published until compatible wheel availability and runtime behavior are validated.

## Packaging

Use `packaging/build_assets.py` to stage a target-specific wheelhouse and build release assets. The default repository index skips this package while `repository.json` has `"publish": false`.

