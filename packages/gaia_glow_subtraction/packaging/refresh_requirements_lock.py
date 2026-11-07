#!/usr/bin/env python3
"""Refresh the Gaia Glow Subtraction hash-locked requirements file.

The bundled AfterNight Python runtime stages NumPy and SciPy into the extension environment, so they are left out of
the lock. Everything else the port imports (Astropy, astropy-healpix, requests, psutil) is resolved recursively from
the wheels' metadata for each runtime target, hashed, and written as one cross-target lock. The host installs with
``--no-deps`` from that lock; the package itself redistributes no wheel.

Usage::

    python3 packages/gaia_glow_subtraction/packaging/refresh_requirements_lock.py --download-dir /tmp/ggs-wheels
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import defaultdict, deque
from dataclasses import dataclass
from email.parser import Parser
from pathlib import Path

from packaging.requirements import Requirement


PYTHON_VERSION = "3.14"
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TOP_LEVEL_SPECS = ["astropy==8.0.2", "astropy-healpix==2.0.1", "requests==2.34.2", "psutil==7.2.2"]
BUNDLED_RUNTIME_PACKAGES = {"numpy", "scipy"}
ABIS = ("cp314", "abi3", "none")


@dataclass(frozen=True)
class WheelTarget:
    runtime_target: str
    pip_platforms: tuple[str, ...]
    marker_environment: dict[str, str]


TARGETS = (
    WheelTarget(
        "linux-clang-x86_64",
        ("manylinux_2_28_x86_64", "manylinux_2_17_x86_64", "manylinux2014_x86_64", "any"),
        {
            "implementation_name": "cpython",
            "platform_machine": "x86_64",
            "platform_python_implementation": "CPython",
            "platform_system": "Linux",
            "python_full_version": "3.14.0",
            "python_version": "3.14",
            "sys_platform": "linux",
            "os_name": "posix",
        },
    ),
    WheelTarget(
        "windows-msvc-x86_64",
        ("win_amd64", "any"),
        {
            "implementation_name": "cpython",
            "platform_machine": "AMD64",
            "platform_python_implementation": "CPython",
            "platform_system": "Windows",
            "python_full_version": "3.14.0",
            "python_version": "3.14",
            "sys_platform": "win32",
            "os_name": "nt",
        },
    ),
)


def canonical(name):
    return name.strip().lower().replace("_", "-")


def wheel_metadata(wheel):
    with zipfile.ZipFile(wheel) as archive:
        member = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
        metadata = Parser().parsestr(archive.read(member).decode("utf-8", "replace"))
    return canonical(metadata["Name"]), metadata["Version"].strip(), metadata.get_all("Requires-Dist", [])


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_wheel(target, spec, destination):
    command = [sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--no-deps", "--implementation", "cp"]
    command += ["--python-version", PYTHON_VERSION]
    for abi in ABIS:
        command += ["--abi", abi]
    for platform in target.pip_platforms:
        command += ["--platform", platform]
    with tempfile.TemporaryDirectory() as tmp:
        process = subprocess.run([*command, "--dest", tmp, spec], capture_output=True, text=True, check=False)
        wheels = sorted(Path(tmp).glob("*.whl"))
        if process.returncode != 0 or not wheels:
            raise RuntimeError(f"No wheel for {spec} on {target.runtime_target}:\n{process.stdout}{process.stderr}")
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / wheels[0].name
        if not path.exists():
            shutil.copy2(wheels[0], path)
        return path


def resolve(target, destination):
    """Download every wheel the top-level specs need on ``target``; return {name: (version, path)}."""

    pending = deque(TOP_LEVEL_SPECS)
    resolved = {}
    while pending:
        requirement = Requirement(pending.popleft())
        name = canonical(requirement.name)
        if name in BUNDLED_RUNTIME_PACKAGES or name in resolved:
            continue
        wheel = download_wheel(target, str(requirement), destination)
        actual, version, requires = wheel_metadata(wheel)
        resolved[actual] = (version, wheel)
        for line in requires:
            dependency = Requirement(line)
            if dependency.marker is not None and not dependency.marker.evaluate(dict(target.marker_environment)):
                continue
            if canonical(dependency.name) not in resolved:
                pending.append(f"{dependency.name}{dependency.specifier}")
    return resolved


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--download-dir", type=Path, help="Keep the downloaded wheels here instead of a temporary dir.")
    args = parser.parse_args()

    versions = {}
    hashes = defaultdict(set)
    with tempfile.TemporaryDirectory() as tmp:
        root = args.download_dir or Path(tmp)
        for target in TARGETS:
            for name, (version, wheel) in resolve(target, root / target.runtime_target).items():
                if versions.setdefault(name, version) != version:
                    raise RuntimeError(f"{name} resolves to {versions[name]} and {version} on different targets")
                hashes[name].add(sha256_file(wheel))

    lines = [
        "# Generated by packages/gaia_glow_subtraction/packaging/refresh_requirements_lock.py",
        "# Hash-locked PyPI install set. Public PyPI wheels are downloaded by the host during install;",
        "# NumPy and SciPy come from the bundled AfterNight runtime.",
        "",
    ]
    for name in sorted(versions):
        pins = " ".join(f"--hash=sha256:{value}" for value in sorted(hashes[name]))
        lines.append(f"{name}=={versions[name]} {pins}")
    lock = PACKAGE_ROOT / "package" / "requirements.lock"
    lock.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {lock} with {len(versions)} packages")


if __name__ == "__main__":
    main()
