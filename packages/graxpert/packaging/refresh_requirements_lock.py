#!/usr/bin/env python3
"""Refresh the GraXpert hash-locked requirements file.

The bundled AfterNight Python runtime already stages NumPy, SciPy, and
scikit-image into the extension environment. GraXpert itself declares a tighter
NumPy upper bound than the runtime currently ships, so the host install runs
with `--no-deps` and every required distribution, including the root GraXpert
wheel, is enumerated explicitly in the generated lockfile.

This script resolves the wheel set recursively with `pip download --no-deps`
so it can inspect wheel metadata, calculate artifact hashes, and write a
cross-target lock file. Official package assets do not redistribute these
public PyPI wheels; the host later installs the hash-locked artifacts from PyPI.
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
from contextlib import nullcontext
from dataclasses import dataclass
from email.parser import Parser
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version


PYTHON_VERSION = "3.14"
PYTHON_ABI = "cp314"
GRAxPERT_SPEC = "graxpert==3.2.0a2"
PACKAGE_ROOT = Path(__file__).resolve().parents[1]

# These packages are staged from the bundled AfterNight runtime instead of the
# GraXpert dependency context. `skimage` is included as a defensive alias for
# `scikit-image` because the manifest uses the stable package-prefix shorthand.
BUNDLED_RUNTIME_PACKAGES = {
    "numpy",
    "scipy",
    "scikit-image",
    "skimage",
}

# AfterNight hosts GraXpert through PySide6, so the standalone Tk frontend is
# not part of the extension dependency context.
IGNORED_PACKAGES = {
    "customtkinter",
}

# GraXpert imports `packaging` directly even though that dependency is not
# declared in the wheel metadata, so seed it explicitly.
EXPLICIT_TOP_LEVEL_SPECS = [
    "onnxruntime-gpu[cuda,cudnn]==1.24.4",
    "packaging==26.1",
]

# Two upstream pins need runtime-target overrides for cp314:
# - `opencv-python-headless==4.11.0.86` is not published for the cp314 wheels we
#   ship today, so we pin the first compatible cp314 release instead.
# - `onnxruntime-gpu[cuda,cudnn]==1.24.4` publishes the CUDA/cuDNN side-package
#   wheels required for GPU execution on the AfterNight runtime targets, so keep
#   those extras during recursive dependency resolution.
# - The NVIDIA side packages need explicit cross-target pins because pip will
#   otherwise pick newer Windows-only builds for some packages (for example
#   `nvidia-cudnn-cu12`) that do not publish matching Linux wheels.
OVERRIDE_SPECS = {
    "astropy-iers-data": "astropy-iers-data==0.2026.4.20.0.58.15",
    "cffi": "cffi==2.0.0",
    "opencv-python-headless": "opencv-python-headless==4.13.0.92",
    "onnxruntime-gpu": "onnxruntime-gpu[cuda,cudnn]==1.24.4",
    "nvidia-cublas-cu12": "nvidia-cublas-cu12==12.6.4.1",
    "nvidia-cuda-nvrtc-cu12": "nvidia-cuda-nvrtc-cu12==12.9.86",
    "nvidia-cuda-runtime-cu12": "nvidia-cuda-runtime-cu12==12.9.79",
    "nvidia-cudnn-cu12": "nvidia-cudnn-cu12==9.5.1.17",
    "nvidia-cufft-cu12": "nvidia-cufft-cu12==11.4.1.4",
    "nvidia-curand-cu12": "nvidia-curand-cu12==10.3.7.77",
    "nvidia-nvjitlink-cu12": "nvidia-nvjitlink-cu12==12.9.86",
}


@dataclass(frozen=True)
class WheelTarget:
    runtime_target: str
    pip_platforms: tuple[str, ...]
    marker_environment: dict[str, str]


TARGETS = {
    "linux-clang-x86_64": WheelTarget(
        runtime_target="linux-clang-x86_64",
        pip_platforms=("manylinux_2_28_x86_64", "manylinux2014_x86_64"),
        marker_environment={
            "implementation_name": "cpython",
            "platform_machine": "x86_64",
            "platform_python_implementation": "CPython",
            "platform_system": "Linux",
            "python_full_version": "3.14.0",
            "python_version": "3.14",
            "sys_platform": "linux",
        },
    ),
    "windows-msvc-x86_64": WheelTarget(
        runtime_target="windows-msvc-x86_64",
        pip_platforms=("win_amd64",),
        marker_environment={
            "implementation_name": "cpython",
            "platform_machine": "AMD64",
            "platform_python_implementation": "CPython",
            "platform_system": "Windows",
            "python_full_version": "3.14.0",
            "python_version": "3.14",
            "sys_platform": "win32",
        },
    ),
}


def canonicalize_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def requirement_to_spec(requirement: Requirement) -> str:
    if requirement.specifier:
        return f"{requirement.name}{requirement.specifier}"
    return requirement.name


def read_wheel_metadata(wheel_path: Path) -> tuple[str, str, list[str]]:
    with zipfile.ZipFile(wheel_path) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = Parser().parsestr(
            archive.read(metadata_name).decode("utf-8", "replace")
        )

    name = metadata.get("Name")
    version = metadata.get("Version")
    if not name or not version:
        raise RuntimeError(f"Wheel {wheel_path} is missing Name/Version metadata")

    return canonicalize_name(name), version.strip(), metadata.get_all("Requires-Dist", [])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def applicable_requirement(requirement_line: str,
                           target: WheelTarget,
                           active_extras: set[str] | None = None) -> Requirement | None:
    requirement = Requirement(requirement_line)
    if requirement.marker is not None:
        if requirement.marker.evaluate(environment=target.marker_environment):
            return requirement

        for extra in sorted(active_extras or ()):
            extra_environment = dict(target.marker_environment)
            extra_environment["extra"] = extra
            if requirement.marker.evaluate(environment=extra_environment):
                return requirement

        return None

    return requirement


def validate_requirement(selected_versions: dict[str, str], requirement: Requirement) -> None:
    package_name = canonicalize_name(requirement.name)
    if package_name not in selected_versions or not requirement.specifier:
        return

    selected_version = Version(selected_versions[package_name])
    if selected_version not in requirement.specifier:
        raise RuntimeError(
            f"Resolved {package_name}=={selected_versions[package_name]} does not satisfy "
            f"{requirement.specifier}"
        )


def pip_download_single(target: WheelTarget, spec: str, destination: Path) -> Path:
    last_error = ""
    for platform in target.pip_platforms:
        with tempfile.TemporaryDirectory() as tmpdir:
            command = [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--dest",
                tmpdir,
                "--only-binary=:all:",
                "--no-deps",
                "--implementation",
                "cp",
                "--python-version",
                PYTHON_VERSION,
                "--abi",
                PYTHON_ABI,
                "--platform",
                platform,
                spec,
            ]
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            if process.returncode != 0:
                last_error = (process.stdout + process.stderr).strip()
                continue

            wheels = sorted(Path(tmpdir).glob("*.whl"))
            if not wheels:
                last_error = f"No wheel produced for {spec} on {platform}"
                continue

            wheel_path = wheels[0]
            destination_path = destination / wheel_path.name
            if not destination_path.exists():
                shutil.copy2(wheel_path, destination_path)
            return destination_path

    raise RuntimeError(
        f"Failed to download a wheel for {spec} on {target.runtime_target}.\n{last_error}"
    )


def resolve_target(target: WheelTarget, download_dir: Path) -> None:
    pending = deque([GRAxPERT_SPEC, *EXPLICIT_TOP_LEVEL_SPECS])
    queued_specs: set[str] = set(pending)
    selected_versions: dict[str, str] = {}
    processed_base_requirements: set[str] = set()
    processed_extras: dict[str, set[str]] = defaultdict(set)
    requires_dist_cache: dict[str, list[str]] = {}

    while pending:
        spec = pending.popleft()
        requirement = Requirement(spec)
        package_name = canonicalize_name(requirement.name)

        if package_name in IGNORED_PACKAGES or package_name in BUNDLED_RUNTIME_PACKAGES:
            continue

        resolved_spec = OVERRIDE_SPECS.get(package_name, spec)
        resolved_requirement = Requirement(resolved_spec)
        validate_requirement(selected_versions, resolved_requirement)
        active_extras = set(resolved_requirement.extras or requirement.extras)

        if package_name not in requires_dist_cache:
            wheel_path = pip_download_single(target, resolved_spec, download_dir)
            actual_name, version, requires_dist = read_wheel_metadata(wheel_path)
            selected_versions[actual_name] = version
            requires_dist_cache[actual_name] = requires_dist
            package_name = actual_name
        else:
            requires_dist = requires_dist_cache[package_name]

        walk_base_requirements = package_name not in processed_base_requirements
        if walk_base_requirements:
            processed_base_requirements.add(package_name)

        new_extras = active_extras.difference(processed_extras[package_name])
        if new_extras:
            processed_extras[package_name].update(new_extras)

        if not walk_base_requirements and not new_extras:
            continue

        for requirement_line in requires_dist:
            dependency = applicable_requirement(requirement_line, target, active_extras)
            if dependency is None:
                continue

            dependency_name = canonicalize_name(dependency.name)
            if dependency_name in IGNORED_PACKAGES or dependency_name in BUNDLED_RUNTIME_PACKAGES:
                continue

            validate_requirement(selected_versions, dependency)

            dependency_spec = OVERRIDE_SPECS.get(
                dependency_name, requirement_to_spec(dependency)
            )
            if dependency_spec in queued_specs:
                continue

            pending.append(dependency_spec)
            queued_specs.add(dependency_spec)


def collect_lock_entries(
    download_dir: Path,
) -> tuple[dict[str, str], dict[str, set[str]], list[str]]:
    versions: dict[str, str] = {}
    hashes: dict[str, set[str]] = defaultdict(set)
    excluded: list[str] = []

    for wheel_path in sorted(download_dir.glob("*.whl")):
        package_name, version, _ = read_wheel_metadata(wheel_path)
        if package_name in BUNDLED_RUNTIME_PACKAGES:
            excluded.append(package_name)
            continue

        existing_version = versions.get(package_name)
        if existing_version is not None and existing_version != version:
            raise RuntimeError(
                f"Multiple versions downloaded for {package_name}: "
                f"{existing_version} and {version}"
            )

        versions[package_name] = version
        hashes[package_name].add(sha256_file(wheel_path))

    return versions, hashes, excluded


def write_lockfile(
    lock_path: Path,
    versions: dict[str, str],
    hashes: dict[str, set[str]],
) -> None:
    lines = [
        "# Generated by packages/graxpert/packaging/refresh_requirements_lock.py",
        "# Hash-locked PyPI install set. Public PyPI wheels are downloaded by the host during install.",
        "",
    ]
    for package_name in sorted(versions):
        hash_args = " ".join(
            f"--hash=sha256:{hash_value}" for hash_value in sorted(hashes[package_name])
        )
        lines.append(f"{package_name}=={versions[package_name]} {hash_args}".rstrip())
    lines.append("")
    lock_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve GraXpert wheels and generate requirements.lock."
    )
    parser.add_argument(
        "--target",
        dest="targets",
        action="append",
        choices=sorted(TARGETS),
        help="Runtime target to prepare. Defaults to both supported targets.",
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=None,
        help="Optional directory for downloaded wheel artifacts. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--lockfile",
        type=Path,
        default=PACKAGE_ROOT / "package" / "requirements.lock",
        help="Hashed lockfile path to write.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete existing wheels in --download-dir before downloading.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected_targets = args.targets or sorted(TARGETS)
    lockfile = args.lockfile.resolve()

    lockfile.parent.mkdir(parents=True, exist_ok=True)
    download_context = (
        tempfile.TemporaryDirectory()
        if args.download_dir is None
        else nullcontext(str(args.download_dir.resolve()))
    )

    with download_context as download_root:
        download_dir = Path(download_root)
        download_dir.mkdir(parents=True, exist_ok=True)

        if args.clean:
            for wheel_path in download_dir.glob("*.whl"):
                wheel_path.unlink()

        for target_name in selected_targets:
            resolve_target(TARGETS[target_name], download_dir)

        versions, hashes, excluded_names = collect_lock_entries(download_dir)
        write_lockfile(lockfile, versions, hashes)

        print(f"Wrote {lockfile}")
        print(f"Prepared {len(versions)} locked distributions")
        if args.download_dir is not None:
            print(f"Downloaded wheel artifacts in {download_dir}")

    if excluded_names:
        print(
            "Skipped bundled-runtime wheels from requirements.lock: "
            f"{', '.join(sorted(set(excluded_names)))}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
