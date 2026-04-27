#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from afternight_repo.package_tools import (  # noqa: E402
    PackageToolError,
    build_package,
    is_package_published,
)


def main():
    parser = argparse.ArgumentParser(description="Build assets for published repository packages.")
    parser.add_argument("--packages-root", default="packages", help="Directory containing package folders")
    parser.add_argument("--output-dir", default="dist", help="Directory where assets are written")
    args = parser.parse_args()

    packages_root = Path(args.packages_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    built_assets = []
    for package_source in sorted(packages_root.glob("*/package")):
        if not (package_source / "extension.json").is_file():
            continue

        package_root = package_source.parent
        if not is_package_published(package_root):
            continue

        custom_builder = package_root / "packaging" / "build_assets.py"
        if custom_builder.is_file():
            result = subprocess.run(
                [sys.executable, str(custom_builder), "--output-dir", str(output_dir)],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if result.returncode != 0:
                print(result.stdout, end="")
                print(result.stderr, end="", file=sys.stderr)
                return result.returncode
            if result.stdout.strip():
                built_assets.extend(json.loads(result.stdout))
            continue

        try:
            built_assets.append(build_package(package_source, output_dir))
        except PackageToolError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    print(json.dumps(built_assets, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
