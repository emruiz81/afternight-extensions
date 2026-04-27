# Workflows

`validate.yml` is the first Phase 6 repository gate. It:

- installs `zstd`
- runs package-tool unit tests
- builds every `packages/*/package` source tree into deterministic `.tar.zst` assets
- verifies generated sidecar hashes against compressed assets
- regenerates `index.json` and diffs it against the checked-in file

Release publication workflows are still future work. They should reuse the same builder and generator instead of creating archives directly in workflow shell.
