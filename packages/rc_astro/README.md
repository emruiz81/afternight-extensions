# RC-Astro XTerminators

This package exposes RC-Astro BlurXTerminator, StarXTerminator, and NoiseXTerminator through AfterNight's native extension process window.

The package contains AfterNight adapter code only. It does not bundle RC-Astro binaries, models, icons, license text, activation credentials, captured product schemas, or private URLs. Users install and license the RC-Astro CLI separately, then select the user-installed RC-Astro CLI executable in AfterNight or use **Detect Installation**.

The package is published through the official AfterNight extension index as `rc_astro`.

## Processes

- RC-Astro BlurXTerminator
- RC-Astro StarXTerminator
- RC-Astro NoiseXTerminator

## Local Testing

Automated tests use synthetic schemas and fake `rc-astro` executables. Real RC-Astro smoke testing requires a user-installed CLI and valid user activation outside this repository.

After installing the local package in AfterNight, open the extension settings. **CLI Connection** shows the resolved status and CLI version; use **Detect Installation** or browse to the RC-Astro executable. The resolver checks the selected executable, common install paths, `CLI`/`bin` subfolders, PATH, and known RC-Astro CLI executable names. Product activation statuses are checked when the settings dialog opens; use **Refresh Status** after changing the executable.

The **Products** card shows BlurXTerminator, StarXTerminator, and NoiseXTerminator activation status rows. Use **Activation...** to open the dedicated activation dialog, choose the product, enter the activation email/key, and run activation while the dialog shows the sanitized CLI output. Process windows inspect the saved settings during startup, try schema-only CLI command variants, and fall back to parsing `rc-astro <product>` help output before showing a schema-unavailable diagnostic. Processing uses the public RC-Astro CLI shape with a positional input path, `-o` output, and `--overwrite`.

The extension settings **Check Updates** action runs the RC-Astro update check and prints CLI output in the **Updates** console area. When the CLI reports a newer version, the **Update** action is enabled and runs the documented `rc-astro update --install` command. The command is never run during automated tests; tests use a fake CLI fixture.

Each process window includes **Model Version** in its **Engine** section. It lists model versions for that RC-Astro product and uses the latest model by default. When a whole version such as `3` is pinned and the CLI only covers a fractional bugfix release of it (for example NoiseXTerminator `3.1`), the adapter passes the covered release; a version the CLI does not cover is reported before the CLI runs.

The adapter reads the RC-Astro CLI parameter document from `rc-astro <product> --json` and accepts every schema version from v1 up. Schema versions 5 and 6 (RC-Astro CLI 2.x) are additive, and newer versions are accepted with a logged warning. Commands follow the CLI integration contract: GUI-only and hidden conditional parameters are not passed, parameters disabled by `disabledIf` or pinned by an engaged mode are left to the CLI, and a boolean that defaults on is switched off explicitly. If the JSON document is unavailable, the adapter falls back to `rc-astro <product>` help text and passes only the options the process window supplied.

For schema v4 and newer, the adapter uses the CLI's global `--device` option. The **Acceleration Device** selector lists the devices from `rc-astro --device --json` and always includes **Automatically select device**, which lets RC-Astro use its own default accelerator behavior. AfterNight caches the process-window parameters when the package is installed or updated, so the adapter queries the CLI for devices at that point when no saved device catalog exists. If no CLI can be queried, the selector offers the documented `gpu0`, `gpu1`, and `cpu` designators. Older schema v3 CLIs that still report `--engine` remain supported for local compatibility.

BlurXTerminator exposes the imaging controls used by the reference RC-Astro integrations. Controls are grouped into **Stellar Adjustments**, **Non stellar adjustments**, **Options**, and **Engine**. The native Reset button restores the curated defaults: Sharpen Stars `0.5`, Adjust Star Halos `0.0`, Auto nonstellar radius enabled, Sharpen Nonstellar `0.5`, Correct Only disabled, device `default`, and overlap `0.2`. Auto nonstellar radius disables the manual Nonstellar Radius control. On RC-Astro CLI 2.x these controls map to the CLI's Automatic PSF (`--ansp`) and PSF Diameter (`--nsd`) options. **Correct Only** disables the sharpening and PSF controls while keeping acceleration device, model version, and tile overlap available. Technical output controls such as CLI output `depth` are hidden from the generated UI; the adapter lets the CLI preserve the temporary FITS handoff depth by default.

StarXTerminator's **Generate Stars Image** option passes `--stars`; the adapter opens the stars-only image the CLI writes next to the starless output.

All three processes use temporary FITS files for the RC-Astro CLI handoff. After processing, the adapter restores the original image metadata to the AfterNight destination image while leaving structural FITS keys such as `BITPIX` and `NAXIS*` to be regenerated from the actual output pixels.
