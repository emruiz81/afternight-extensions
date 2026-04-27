# Workflows

Planned GitHub Actions workflows:

- validate package manifests and layouts on pull requests
- build target-specific package archives
- verify SHA-256 package hashes
- generate and publish `index.json`
- publish package archives as GitHub Release assets

CI should treat `index.json` as generated metadata once the generator lands.
