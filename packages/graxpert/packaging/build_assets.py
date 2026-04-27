#!/usr/bin/env python3
"""Build target-specific GraXpert package assets."""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SOURCE = PACKAGE_ROOT / "package"
PACKAGE_ID = "graxpert"
TARGETS = ("linux-clang-x86_64", "windows-msvc-x86_64")

sys.path.insert(0, str(REPO_ROOT / "tools"))

from afternight_repo.package_tools import build_package, read_json  # noqa: E402


def is_universal_wheel(name):
    return name.endswith("-none-any.whl")


def is_target_wheel(name, target):
    if is_universal_wheel(name):
        return True
    if target == "linux-clang-x86_64":
        return "manylinux" in name or "linux_x86_64" in name
    if target == "windows-msvc-x86_64":
        return "win_amd64" in name
    return False


def copy_package_source(destination):
    def ignore(directory, names):
        del directory
        ignored = {"__pycache__", "wheelhouse"}
        ignored.update(name for name in names if name.endswith((".pyc", ".pyo")))
        return ignored

    shutil.copytree(PACKAGE_SOURCE, destination, ignore=ignore)
    (destination / "wheelhouse").mkdir(parents=True, exist_ok=True)


def copy_existing_wheelhouse(source_wheelhouse, target, destination):
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for wheel in sorted(Path(source_wheelhouse).glob("*.whl")):
        if not is_target_wheel(wheel.name, target):
            continue
        shutil.copy2(wheel, destination / wheel.name)
        copied += 1

    if copied == 0:
        raise RuntimeError(f"No compatible wheels found for {target} in {source_wheelhouse}")


def prepare_downloaded_wheelhouse(target, staged_package):
    command = [
        sys.executable,
        str(PACKAGE_ROOT / "packaging" / "prepare_wheelhouse.py"),
        "--target",
        target,
        "--wheelhouse",
        str(staged_package / "wheelhouse"),
        "--lockfile",
        str(staged_package / "requirements.lock"),
        "--clean",
    ]
    result = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.stdout:
        print(result.stdout, end="", file=sys.stderr)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"prepare_wheelhouse.py failed for {target}")


def build_target(args, target):
    manifest = read_json(PACKAGE_SOURCE / "extension.json")
    with tempfile.TemporaryDirectory() as temp:
        staged_package = Path(temp) / PACKAGE_ID
        copy_package_source(staged_package)

        if args.source_lockfile:
            shutil.copy2(args.source_lockfile, staged_package / "requirements.lock")

        if args.source_wheelhouse:
            copy_existing_wheelhouse(
                args.source_wheelhouse,
                target,
                staged_package / "wheelhouse",
            )
        elif args.download_wheelhouse:
            prepare_downloaded_wheelhouse(target, staged_package)
        else:
            raise RuntimeError(
                "GraXpert assets need --source-wheelhouse for local reuse or --download-wheelhouse "
                "to resolve the target wheelhouse."
            )

        return build_package(
            staged_package,
            args.output_dir,
            compression_level=args.compression_level,
            runtime_targets=[target],
            asset_name=f"{PACKAGE_ID}-{manifest['version']}-{target}.tar.zst",
        )


def main():
    parser = argparse.ArgumentParser(description="Build GraXpert target-specific package assets.")
    parser.add_argument("--output-dir", default="dist", help="Directory where assets are written")
    parser.add_argument(
        "--target",
        dest="targets",
        action="append",
        choices=TARGETS,
        help="Runtime target to build. Defaults to all staged targets.",
    )
    parser.add_argument("--compression-level", type=int, default=10, help="zstd compression level, 1-19")
    parser.add_argument("--source-wheelhouse", type=Path, help="Existing wheelhouse to filter by target")
    parser.add_argument("--source-lockfile", type=Path, help="Existing requirements.lock to copy into staged assets")
    parser.add_argument(
        "--download-wheelhouse",
        action="store_true",
        help="Download a fresh target wheelhouse with prepare_wheelhouse.py",
    )
    args = parser.parse_args()

    if args.source_wheelhouse and args.download_wheelhouse:
        parser.error("--source-wheelhouse and --download-wheelhouse are mutually exclusive")

    args.output_dir = Path(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        assets = [build_target(args, target) for target in (args.targets or TARGETS)]
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(assets, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
