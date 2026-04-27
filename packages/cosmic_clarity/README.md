# Cosmic Clarity

Cosmic Clarity exposes Seti Astro's Cosmic Clarity suite inside AfterNight through the Python extension runtime.

This package contains the AfterNight adapter only. Users still configure the location of their Cosmic Clarity installation from the process window. The upstream helper executables and their model/runtime payloads are not redistributed in this repository package.

## Processes

- Cosmic Clarity Denoise
- Cosmic Clarity Dark Star
- Cosmic Clarity Super Resolution
- Cosmic Clarity Sharpening

## Runtime Targets

This adapter is pure Python and supports the current AfterNight runtime targets:

- `linux-clang-x86_64`
- `windows-msvc-x86_64`
- `windows-msys2-x86_64`

The selected Cosmic Clarity helper installation must be compatible with the user's operating system.

