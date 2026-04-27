# Workflows

`validate.yml` is the first Phase 6 repository gate. It:

- installs `zstd`
- runs package-tool unit tests
- builds published package source trees into deterministic `.tar.zst` assets
- skips source-staged packages marked with `"publish": false`
- verifies generated sidecar hashes against compressed assets
- regenerates `index.json` and diffs it against the checked-in file

Release publication workflows are still future work. They should reuse the same builder and generator instead of creating archives directly in workflow shell.
