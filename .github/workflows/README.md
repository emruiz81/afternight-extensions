# Workflows

`validate.yml` is the first Phase 6 repository gate. It:

- installs `zstd`
- runs package-tool unit tests
- builds published package source trees into deterministic `.tar.zst` assets
- skips source-staged packages marked with `"publish": false`
- verifies generated sidecar hashes against compressed assets
- regenerates `index.json` and diffs it against the checked-in file
- checks out the AfterNight validator source, builds the focused Linux `Test_ProcessFramework` binary, and runs the app-side package/index validator against this repository checkout

Release publication workflows are still future work. They should reuse the same builder and generator instead of creating archives directly in workflow shell.

The app-side validator checkout defaults to `emruiz81/afternight@extensions_sdk` while Phase 6 is developed on the SDK branch. Set repository variables `AFTERNIGHT_VALIDATOR_REPOSITORY` and `AFTERNIGHT_VALIDATOR_REF` to point the gate at another repository/ref, such as `main` after the SDK branch lands there.

`build-assets.yml` is a manual workflow for producing package assets before the repository is public. It can build:

- all currently published packages
- Cosmic Clarity by itself
- GraXpert target-specific assets by resolving the generated wheelhouse in CI

The workflow uploads `.tar.zst` files and sidecars as GitHub Actions artifacts. It does not create a GitHub Release.
