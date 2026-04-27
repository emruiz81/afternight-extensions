#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from afternight_repo.package_tools import PackageToolError, build_package  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Build a deterministic AfterNight .tar.zst package asset.")
    parser.add_argument("package_dir", help="Path to packages/<extension_id>/package")
    parser.add_argument("--output-dir", default="dist", help="Directory where assets are written")
    parser.add_argument(
        "--runtime-target",
        action="append",
        dest="runtime_targets",
        help="Runtime target to include; may be repeated. Defaults to manifest runtime_targets.",
    )
    parser.add_argument("--compression-level", type=int, default=10, help="zstd compression level, 1-19")
    parser.add_argument("--asset-name", help="Override generated asset file name")
    args = parser.parse_args()

    try:
        metadata = build_package(
            args.package_dir,
            args.output_dir,
            compression_level=args.compression_level,
            runtime_targets=args.runtime_targets,
            asset_name=args.asset_name,
        )
    except PackageToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

