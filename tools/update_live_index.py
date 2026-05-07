#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Ezequiel Ruiz

import argparse
import copy
import json
import sys
from pathlib import Path


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, data):
    with Path(path).open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def update_live_index(candidate_index, package_id, current_live_index=None):
    candidate_package = next(
        (
            package
            for package in candidate_index.get("extensions", [])
            if isinstance(package, dict) and package.get("id") == package_id
        ),
        None,
    )
    if candidate_package is None:
        raise ValueError(f"candidate index does not contain package {package_id}")

    if current_live_index is None:
        return {
            "schema_version": candidate_index["schema_version"],
            "repository": candidate_index["repository"],
            "official": candidate_index.get("official", True),
            "updated_at": candidate_index["updated_at"],
            "extensions": [copy.deepcopy(candidate_package)],
        }

    live = copy.deepcopy(current_live_index)
    live_by_id = {
        package.get("id"): package
        for package in live.get("extensions", [])
        if isinstance(package, dict) and package.get("id")
    }
    live_by_id[package_id] = copy.deepcopy(candidate_package)

    live["schema_version"] = candidate_index["schema_version"]
    live["repository"] = candidate_index["repository"]
    live["official"] = candidate_index.get("official", True)
    live["updated_at"] = candidate_index["updated_at"]

    ordered = []
    for package in candidate_index.get("extensions", []):
        package_id_value = package.get("id") if isinstance(package, dict) else None
        if package_id_value in live_by_id:
            ordered.append(live_by_id.pop(package_id_value))

    ordered.extend(live_by_id[key] for key in sorted(live_by_id))
    live["extensions"] = ordered
    return live


def main():
    parser = argparse.ArgumentParser(description="Merge a package release into the live extension index.")
    parser.add_argument("--candidate-index", required=True, help="Generated candidate index from the release commit")
    parser.add_argument("--current-live-index", help="Existing live index to update")
    parser.add_argument("--package-id", required=True, help="Package id being published by this release run")
    parser.add_argument("--output", required=True, help="Path to write the merged live index")
    args = parser.parse_args()

    try:
        candidate_index = read_json(args.candidate_index)
        current_live_index = read_json(args.current_live_index) if args.current_live_index else None
        live_index = update_live_index(candidate_index, args.package_id, current_live_index)
        write_json(args.output, live_index)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
