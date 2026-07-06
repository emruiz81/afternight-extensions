# RC-Astro XTerminators

This staged package exposes RC-Astro BlurXTerminator, StarXTerminator, and NoiseXTerminator through AfterNight's native extension process window.

The package contains AfterNight adapter code only. It does not bundle RC-Astro binaries, models, icons, license text, activation credentials, captured product schemas, or private URLs. Users install and license the RC-Astro CLI separately, then select the user-installed RC-Astro CLI executable in AfterNight or use **Detect Installation**.

`repository.json` is set to `"publish": false`, so this package can be built and tested locally without entering the generated public candidate index.

## Processes

- RC-Astro BlurXTerminator
- RC-Astro StarXTerminator
- RC-Astro NoiseXTerminator

## Local Testing

Automated tests use synthetic schemas and fake `rc-astro` executables. Real RC-Astro smoke testing requires a user-installed CLI and valid user activation outside this repository.

After installing the local package in AfterNight, open the extension settings. **CLI Connection** shows the resolved status and CLI version; use **Detect Installation** or browse to the RC-Astro executable. The resolver checks the selected executable, common install paths, `CLI`/`bin` subfolders, PATH, and known RC-Astro CLI executable names. Product activation statuses are checked when the settings dialog opens; use **Refresh Status** after changing the executable.

The **Products** card shows BlurXTerminator, StarXTerminator, and NoiseXTerminator activation status rows. Choose the product to activate, enter the activation email/key, and use **Activate Selected Product**. Process windows inspect the saved settings during startup, try schema-only CLI command variants, and fall back to parsing `rc-astro <product>` help output before showing a schema-unavailable diagnostic. Processing uses the public RC-Astro CLI shape with a positional input path, `-o` output, and `--overwrite`.

The extension settings **Check Updates** action runs the RC-Astro update check. When the CLI reports a newer version, the **Update** action is enabled and runs the documented `rc-astro update --install` command. The command is never run during automated tests; tests use a fake CLI fixture.

Each process window includes **Model Version** in its **Engine** section. It lists schema-reported model versions for that RC-Astro product and uses the latest model by default. For RC-Astro CLI 0.9.9 and newer, the adapter also accepts schema v4 and uses the CLI's `--device` accelerator selection option. Older schema v3 CLIs that still report `--engine` remain supported for local compatibility.

BlurXTerminator exposes the imaging controls used by the reference RC-Astro integrations. Controls are grouped into **Stellar Adjustments**, **Non stellar adjustments**, **Options**, and **Engine**. The native Reset button restores the curated defaults: Sharpen Stars `0.5`, Adjust Star Halos `0.0`, Auto nonstellar radius enabled, Sharpen Nonstellar `0.5`, Correct Only disabled, device `default`, and overlap `0.2`. Auto nonstellar radius disables the manual Nonstellar Radius control. **Correct Only** disables the sharpening and PSF controls while keeping acceleration device, model version, and tile overlap available. Technical output controls such as CLI output `depth` are hidden from the generated UI; the adapter lets the CLI preserve the temporary FITS handoff depth by default.
