# RC-Astro XTerminators

This staged package exposes RC-Astro BlurXTerminator, StarXTerminator, and NoiseXTerminator through AfterNight's native extension process window.

The package contains AfterNight adapter code only. It does not bundle RC-Astro binaries, models, icons, license text, activation credentials, captured product schemas, or private URLs. Users install and license the RC-Astro CLI separately, then configure the RC-Astro installation folder, `CLI` folder, or `bin` folder in AfterNight.

`repository.json` is set to `"publish": false`, so this package can be built and tested locally without entering the generated public candidate index.

## Processes

- RC-Astro BlurXTerminator
- RC-Astro StarXTerminator
- RC-Astro NoiseXTerminator

## Local Testing

Automated tests use synthetic schemas and fake `rc-astro` executables. Real RC-Astro smoke testing requires a user-installed CLI and valid user activation outside this repository.

After installing the local package in AfterNight, open the extension settings, use **Detect Installation** or select the RC-Astro installation folder. The resolver checks common install paths, `CLI`/`bin` subfolders, PATH, and known RC-Astro CLI executable names. Use **Refresh Status** after changing the folder. The settings page should show the resolved executable, CLI version, detection source, and activation status reported by the installed CLI. Process windows inspect the saved settings during startup, try schema-only CLI command variants, and fall back to parsing `rc-astro <product>` help output before showing a schema-unavailable diagnostic. Processing uses the public RC-Astro CLI shape with a positional input path, `-o` output, and `--overwrite`.

Each process window includes a **Models** section. It lists the schema-reported model versions for that RC-Astro product, lets the run use the latest model or a fixed version, and exposes model download / force-redownload actions near the product controls instead of in the shared extension settings.

BlurXTerminator exposes the imaging controls used by the reference RC-Astro integrations. Controls are grouped into **Stellar Adjustments**, **Non stellar adjustments**, and **Options**. The native Reset button restores the curated defaults: Sharpen Stars `0.5`, Adjust Star Halos `0.0`, Auto nonstellar radius enabled, Sharpen Nonstellar `0.5`, Correct Only disabled, engine `auto`, and overlap `0.2`. Auto nonstellar radius disables the manual Nonstellar Radius control. **Correct Only** disables the sharpening and PSF controls while keeping inference engine and tile overlap available. Technical output controls such as CLI output `depth` are hidden from the generated UI; the adapter lets the CLI preserve the temporary FITS handoff depth by default.
