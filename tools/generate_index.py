#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from afternight_repo.package_tools import PackageToolError, generate_index, write_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Generate the AfterNight extension repository index.")
    parser.add_argument("--packages-root", default="packages", help="Directory containing package folders")
    parser.add_argument("--assets-dir", default="dist", help="Directory containing built .tar.zst assets")
    parser.add_argument("--repository", default="afternight-extensions", help="Repository id for index.json")
    parser.add_argument(
        "--updated-at",
        default=None,
        help="UTC timestamp to write into index.json. Defaults to current time.",
    )
    parser.add_argument(
        "--base-url",
        default="https://github.com/emruiz81/afternight-extensions/releases/download/v1.0.0",
        help="Base URL prepended to release asset names",
    )
    parser.add_argument("--output", default="index.json", help="Output index path")
    args = parser.parse_args()

    updated_at = args.updated_at
    if updated_at is None:
        updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    try:
        index = generate_index(
            packages_root=args.packages_root,
            assets_dir=args.assets_dir,
            repository=args.repository,
            updated_at=updated_at,
            base_url=args.base_url,
        )
    except PackageToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    write_json(args.output, index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
