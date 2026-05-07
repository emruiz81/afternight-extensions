#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from afternight_repo.veralux_upstream import (  # noqa: E402
    VeraLuxUpstreamError,
    check_veralux_upstream,
    format_veralux_upstream_report,
)


def main():
    parser = argparse.ArgumentParser(
        description="Check VeraLux UPSTREAM.json against a local siril-scripts git checkout."
    )
    parser.add_argument(
        "--package-dir",
        default="packages/veralux/package",
        help="Path to the VeraLux package directory containing UPSTREAM.json.",
    )
    parser.add_argument(
        "--upstream-checkout",
        required=True,
        help="Path to a local git checkout of https://gitlab.com/free-astro/siril-scripts.git.",
    )
    parser.add_argument(
        "--ref",
        help="Git ref to inspect. Defaults to the package UPSTREAM.json upstream_commit.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    try:
        report = check_veralux_upstream(args.package_dir, args.upstream_checkout, ref=args.ref)
    except (OSError, json.JSONDecodeError, VeraLuxUpstreamError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_veralux_upstream_report(report))
    return 0 if report["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
