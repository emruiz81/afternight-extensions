---
description: "Use when reviewing GitHub workflows, repository docs, package READMEs, or AGENTS guidance. Focus on keeping CI behavior, maintainer instructions, and canonical documentation synchronized."
applyTo: ".github/workflows/**/*.yml,.github/workflows/**/*.yaml,docs/**/*.md,packages/**/*.md,README.md,CONTRIBUTING.md,AGENTS.md"
---

# Workflow And Documentation Review Focus

- Treat `docs/` as canonical when policy wording differs from summaries in
  `AGENTS.md`, package READMEs, or workflow notes.
- Keep the workflow split intact: `validate.yml` is the PR/push gate,
  `build-assets.yml` is preview-only, and `publish-release.yml` is the only
  publication path.
- Pull requests that add a new publishable package must update the static
  `package_id` dropdown in `.github/workflows/publish-release.yml` and keep
  repository tests green.
- Flag documentation changes that describe commands, paths, prerequisites, or
  CI behavior inaccurately. Important prerequisites include `zstd` for
  packaging and the sibling `../afternight` checkout for package-local tests
  and app-side integration checks.
- When workflow behavior changes, require the corresponding documentation or
  AGENTS updates so contributors and reviewers see the same process.
- Prefer comments that call out missing companion docs, stale release steps,
  or mismatches between documented and actual validation behavior.
