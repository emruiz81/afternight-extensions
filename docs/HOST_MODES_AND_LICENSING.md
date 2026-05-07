# Host Modes and Licensing

This document explains how an extension package chooses the AfterNight host process and what that means for licensing review. It is not legal advice; it is the repository policy used for package validation and publication review.

## Host Mode Summary

The `sdk_backend` field in `extension.json` selects the host mode:

| `sdk_backend` | Host mode | AfterNight host process | Engine access | Native AfterNight controls | License policy |
|---|---|---|---|---|---|
| `runtime` | Full hosted | `AfterNightExtensionHost` | Direct `_afternight_runtime` / `AfterNightEngine` | Allowed | GPL-3.0-family only |
| `protocol` | Lite hosted | `AfterNightExtensionHostLite` | None | Not allowed | Non-GPL-capable, subject to package/dependency licenses |
| `rpc` | Lite hosted + SDK sidecar | `AfterNightExtensionHostLite` plus `AfterNightSdkHost` | RPC to GPL Engine sidecar | Not allowed for non-GPL packages | Deferred until AfterNight ships RPC support; subject to legal review |

Existing official packages currently use `sdk_backend = runtime`, so they must remain under a GPL-3.0-family license.

## Full Hosted Packages

Use full hosting when the package needs AfterNight's Engine or native process UI.

Manifest:

```json
{
  "license": "GPL-3.0-or-later",
  "launch_mode": "single_image",
  "sdk_backend": "runtime"
}
```

Full hosted packages may use:

- `_afternight_runtime`
- `afternight.core`
- `afternight.io`
- `afternight.calibration`
- `afternight.registration`
- `afternight.stacking`
- native `ParamDef` process windows and RT-preview controls

Full hosted packages must use a GPL-3.0-family license because they run in the GPL full host and may directly link or load AfterNight Engine/native-control code.

## Lite Hosted Packages

Use lite hosting when the package must avoid AfterNight Engine and native-control linkage.

Manifest:

```json
{
  "license": "MIT",
  "launch_mode": "single_image",
  "sdk_backend": "protocol"
}
```

Lite hosted packages may use host protocol services:

- list open views and read view metadata
- receive view created/removed/renamed/modified callbacks
- request snapshots or shared buffers from views
- return image buffers or files for host-side view creation/update
- attach history metadata to returned results
- use settings, progress, logging, diagnostics, notifications, and host dialogs
- own their UI with PySide6, another Python UI toolkit, a helper process, or no UI

Lite hosted packages must not use:

- `_afternight_runtime`
- Engine-backed `afternight` modules such as `core`, `io`, `registration`, `calibration`, or `stacking`
- native AfterNight controls or `ParamDef`-rendered process windows
- C++ AfterNight SDK types

If a package is non-GPL and imports Engine-backed modules, it is not eligible for lite publication.

## Future RPC Packages

`sdk_backend = rpc` is reserved for the future AfterNight RPC backend. It keeps the extension in the lite host, then sends Engine-domain SDK calls to the GPL `AfterNightSdkHost` sidecar over the shared protocol.

RPC packages are not publishable until the target AfterNight release advertises RPC support. Before then, repository validation should mark them incompatible.

## UI Toolkit Notes

PySide6 is preferred for non-GPL lite custom UI because Qt for Python is available under LGPL/GPL/commercial terms. PyQt6 is GPL/commercial and is not LGPL; non-GPL authors choosing PyQt6 need an appropriate commercial PyQt license.

## Review Checklist

For every package:

- `extension.json` has explicit `license` and `sdk_backend`.
- Package-local `LICENSE` matches the manifest.
- `THIRD_PARTY_NOTICES.md` covers copied source, helper binaries, models, and bundled artifacts.
- `runtime` packages use `GPL-3.0`, `GPL-3.0-only`, or `GPL-3.0-or-later`.
- Non-GPL packages use `protocol` or, after RPC ships, `rpc`.
- Non-GPL packages do not import `_afternight_runtime` or Engine-backed `afternight` modules.
- Lite packages do not declare native-control-only capabilities.
- Public PyPI wheels are hash-locked and installed by the host, not redistributed in package assets.

Primary references:

- GNU GPL FAQ: https://www.gnu.org/licenses/gpl-faq.html
- GNU GPLv3 text: https://www.gnu.org/licenses/gpl-3.0.en.html
- Qt for Python licensing: https://doc.qt.io/qtforpython-6.5/commercial/index.html
- PyQt licensing: https://riverbankcomputing.com/software/pyqt/intro
