#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Ezequiel Ruiz

"""Check ported packages' UPSTREAM.json files against a local upstream git checkout."""

import argparse
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from afternight_repo.upstream import (  # noqa: E402
    UpstreamError,
    check_upstream,
    find_upstream_packages,
    format_upstream_report,
)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Check ported packages' UPSTREAM.json against a local upstream git checkout, such as "
            "https://gitlab.com/free-astro/siril-scripts.git. Without --package-dir, every package under "
            "--packages-root that carries package/UPSTREAM.json is checked."
        )
    )
    parser.add_argument(
        "--package-dir",
        action="append",
        default=[],
        help="Package directory containing UPSTREAM.json. Repeat to check several packages.",
    )
    parser.add_argument(
        "--packages-root",
        default="packages",
        help="Root searched for packages with UPSTREAM.json when --package-dir is omitted.",
    )
    parser.add_argument(
        "--upstream-checkout",
        required=True,
        help="Path to a local git checkout of the upstream repository.",
    )
    parser.add_argument(
        "--ref",
        help="Git ref to inspect. Defaults to each package's UPSTREAM.json upstream_commit.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    package_dirs = [Path(path) for path in args.package_dir] or find_upstream_packages(args.packages_root)
    if not package_dirs:
        print(f"error: no package with UPSTREAM.json found under {args.packages_root}", file=sys.stderr)
        return 1

    reports = []
    for package_dir in package_dirs:
        try:
            reports.append(check_upstream(package_dir, args.upstream_checkout, ref=args.ref))
        except (OSError, json.JSONDecodeError, UpstreamError) as exc:
            print(f"error: {package_dir}: {exc}", file=sys.stderr)
            return 1

    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        print("\n\n".join(format_upstream_report(report) for report in reports))
    return 0 if all(report["success"] for report in reports) else 2


if __name__ == "__main__":
    raise SystemExit(main())
