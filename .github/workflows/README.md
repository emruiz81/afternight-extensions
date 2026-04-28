# Workflows

`validate.yml` is the first Phase 6 repository gate. It:

- installs `zstd`
- runs package-tool unit tests
- builds published package source trees into deterministic `.tar.zst` assets
- skips source-staged packages marked with `"publish": false`
- verifies generated sidecar hashes against compressed assets
- regenerates `index.json` and diffs it against the checked-in file
- optionally checks out the AfterNight validator source, builds the focused Linux `Test_ProcessFramework` binary, and runs the app-side package/index validator against this repository checkout when `AFTERNIGHT_VALIDATOR_ENABLED` is set to `true`

Release publication workflows are still future work. They should reuse the same builder and generator instead of creating archives directly in workflow shell.

The app-side validator is disabled by default because the main `afternight` repository is currently private. Enable it by setting repository variable `AFTERNIGHT_VALIDATOR_ENABLED=true`; for private validator repositories, also set secret `AFTERNIGHT_VALIDATOR_TOKEN` to a token with read access. The checkout defaults to `emruiz81/afternight@extensions_sdk`; set repository variables `AFTERNIGHT_VALIDATOR_REPOSITORY` and `AFTERNIGHT_VALIDATOR_REF` to point the gate at another repository/ref, such as `main` after the SDK branch lands there.

`build-assets.yml` is a manual workflow for producing package assets before the repository is public. It can build:

- all currently published packages
- Cosmic Clarity by itself
- GraXpert's thin PyPI-backed asset without redistributing public wheels

The workflow uploads `.tar.zst` files and sidecars as GitHub Actions artifacts. It does not create a GitHub Release.
