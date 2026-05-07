# Host Modes and Licensing

This document explains how an extension package chooses the AfterNight host process and what that means for licensing review. It is not legal advice; it is the repository policy used for package validation and publication review.

The repository-level license for tooling, documentation, CI configuration,
tests, and non-package templates is Apache-2.0. Extension packages are licensed
separately by their manifest, package-local `LICENSE`, and notices. The
repository-level Apache-2.0 license does not relicense package-local GPL code.

## Host Mode Summary

The `sdk_backend` field in `extension.json` selects the host mode:

| `sdk_backend` | Host mode | AfterNight host process | Engine access | Native AfterNight controls | License policy |
|---|---|---|---|---|---|
| `runtime` | Full hosted | `AfterNightExtensionHost` | Direct `_afternight_runtime` / `AfterNightEngine` | Allowed | GPL-3.0-family only |
| `protocol` | Lite hosted | `AfterNightExtensionHostLite` | None | Not allowed | Non-GPL-capable, subject to package/dependency licenses |
| `rpc` | Lite hosted + SDK sidecar | `AfterNightExtensionHostLite` plus `AfterNightSdkHost` | RPC to GPL Engine sidecar | Not allowed for non-GPL packages | Deferred until AfterNight ships RPC support; subject to legal review |

Existing official packages currently use `sdk_backend = runtime`, so they must remain under a GPL-3.0-family license.

Packages never choose host executable paths. The AfterNight Extension Manager
maps `sdk_backend` to the correct host process, so authors only need to set the
manifest field correctly:

- `runtime` spawns `AfterNightExtensionHost`
- `protocol` spawns `AfterNightExtensionHostLite`
- `rpc` will spawn `AfterNightExtensionHostLite` and verify
  `AfterNightSdkHost` after AfterNight ships RPC support

## Full Hosted Packages

Use full hosting when the package needs AfterNight's Engine or native process UI.

Manifest:

```json
{
  "license": "GPL-3.0-or-later",
  "type": "python",
  "launch_mode": "single_image",
  "sdk_backend": "runtime",
  "package_format_version": 1,
  "protocol_version": 1,
  "sdk_version": 1
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
  "type": "python",
  "launch_mode": "single_image",
  "sdk_backend": "protocol",
  "package_format_version": 1,
  "protocol_version": 1,
  "sdk_version": 1
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

Recommended Python imports for lite packages:

```python
import afternight
from afternight.lite import LiteProcessExtension


class ExampleLiteProcess(LiteProcessExtension):
    def on_launch(self):
        for view in self.list_views():
            self.log_info(f"Open view: {view.get('name')}")
```

## Future RPC Packages

`sdk_backend = rpc` is reserved for the future AfterNight RPC backend. It keeps the extension in the lite host, then sends Engine-domain SDK calls to the GPL `AfterNightSdkHost` sidecar over the shared protocol.

RPC packages are not publishable until the target AfterNight release advertises RPC support. Before then, repository validation should mark them incompatible.

## Allowed Imports By Mode

| Python surface | `runtime` full host | `protocol` lite host | `rpc` future lite host |
|---|---:|---:|---:|
| `afternight`, settings, logging, session metadata | Yes | Yes | Yes |
| `afternight.lite` base classes | Not recommended | Yes | Yes |
| `afternight.ui` native process-window helpers | Yes | No | No for non-GPL packages |
| `_afternight_runtime` | Yes | No | No |
| Engine-backed modules: `core`, `io`, `calibration`, `registration`, `stacking` | Yes | No | Through RPC only after AfterNight ships RPC support |
| Extension-owned PySide6/PyQt6 UI | Yes, but full-host package remains GPL-compatible | Yes | Yes |

## Standalone And Dev Mode

AfterNight exposes socketless dev launches for both host processes:

```bash
AfterNightExtensionHost --standalone --sdk-backend runtime --extension-package-root <package> --entry-point <module> --process-class <class> --environment-root <env> --runtime-root <PythonLib>
AfterNightExtensionHostLite --standalone --sdk-backend protocol --extension-package-root <package> --entry-point <module> --process-class <class> --environment-root <env> --runtime-root <PythonLib>
```

Full standalone mode is a GPL full-host development path and may load the direct
runtime backend. Lite standalone mode provides mock/empty app-view services only
and must not expose loopback Engine services. Lite extensions can inspect
`afternight.current_session().is_standalone` when they need to adjust UI startup
for a socketless dev run.

## Migrating From Full Hosted To Lite Hosted

Move a package from `runtime` to `protocol` only when it can stop using
AfterNight Engine and native-control APIs:

1. Change `sdk_backend` from `runtime` to `protocol`.
2. Change the package license only if the package code and all dependencies
   permit the new license.
3. Replace full-host base classes with `afternight.lite.LiteProcessExtension`
   or `LiteWorkflowExtension`.
4. Remove `_afternight_runtime` and Engine-backed `afternight` imports.
5. Replace native `ParamDef`/`afternight.ui` controls with extension-owned UI
   such as PySide6, another toolkit, a helper process, or no UI.
6. Use protocol-safe app/view services for view metadata, snapshots, shared
   buffers, settings, progress, logging, and result presentation.
7. Test with `AfterNightExtensionHostLite --standalone` and then through the
   Extension Manager.

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
