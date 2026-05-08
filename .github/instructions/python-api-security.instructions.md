---
description: "Use when reviewing or editing Python extension code, tests, or repository tooling. Focus on AfterNight API compliance, host-process security, documentation, and validation coverage."
applyTo: "packages/**/package/**/*.py,packages/**/tests/**/*.py,tools/**/*.py,tests/**/*.py"
---

# Python API And Security Review Focus

- Treat extension code as host-process code. Prefer findings where untrusted
  inputs can reach code execution, shell execution, unsafe deserialization,
  archive extraction, native module loading, or arbitrary file-system writes.
- For `protocol` packages, flag imports of `_afternight_runtime`,
  `afternight.core`, `afternight.io`, `afternight.registration`,
  `afternight.calibration`, `afternight.stacking`, or native `afternight.ui`.
- For `runtime` packages, ensure GPL-3.0-family licensing remains compatible
  with any added code or dependencies.
- Prefer structured subprocess invocation such as `subprocess.run([...],
  check=True, shell=False)`. Flag commands built from untrusted strings,
  PATH-dependent helper execution from temp/user-writable directories, and
  missing validation of downloaded or unpacked executables.
- Flag unsafe use of `pickle`, `marshal`, `yaml.load`, `exec`, `eval`,
  `compile`, `ctypes`, `cffi`, `importlib`, or `__import__` when the target,
  payload, or module name can be influenced by files, settings, package
  metadata, downloaded data, or user-controlled input.
- When code handles paths or archives, look for path traversal, absolute
  paths, symlink handling, unsafe temporary directories, TOCTOU races, writes
  outside the intended work directory, or extraction behavior that conflicts
  with the package format extraction policy.
- Require tests or targeted validation updates when behavior, package loading,
  security checks, or API boundaries change.
- Require documentation updates when maintainers or package authors need new
  rules or procedures to use the change safely.
