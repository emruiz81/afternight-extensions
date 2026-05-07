#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Ezequiel Ruiz

import argparse
import json
import os
import sys
import uuid
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from afternight_repo.package_tools import (  # noqa: E402
    PackageToolError,
    is_package_published,
    load_valid_manifest,
    read_json,
)


OFFICIAL_GITHUB_REPOSITORY = "emruiz81/afternight-extensions"


def list_available_release_metadata(packages_root):
    packages_root = Path(packages_root)
    available = []

    for package_root in sorted(path for path in packages_root.iterdir() if path.is_dir()):
        package_dir = package_root / "package"
        repository_metadata_path = package_root / "repository.json"
        if not package_dir.is_dir() or not repository_metadata_path.is_file():
            continue

        if not is_package_published(package_root):
            continue

        manifest = load_valid_manifest(package_dir)
        repository_metadata = read_json(repository_metadata_path)
        releases = repository_metadata.get("releases")
        if not isinstance(releases, list):
            raise PackageToolError(f"{repository_metadata_path}: releases must be an array")

        versions = []
        for release in releases:
            if not isinstance(release, dict):
                raise PackageToolError(f"{repository_metadata_path}: releases must contain objects")
            version = release.get("version")
            if not isinstance(version, str) or not version:
                raise PackageToolError(
                    f"{repository_metadata_path}: release.version must be a non-empty string"
                )
            versions.append(version)

        latest_version = repository_metadata.get("latest_version", manifest["version"])
        if not isinstance(latest_version, str) or not latest_version:
            raise PackageToolError(f"{repository_metadata_path}: latest_version must be a non-empty string")

        available.append(
            {
                "package_id": manifest["id"],
                "manifest_name": manifest["name"],
                "latest_version": latest_version,
                "versions": versions,
            }
        )

    return available


def resolve_release_metadata(
    packages_root,
    package_id,
    version,
    expected_github_repository=OFFICIAL_GITHUB_REPOSITORY,
):
    _validate_package_id(package_id)
    packages_root = Path(packages_root)
    package_root = packages_root / package_id
    package_dir = package_root / "package"
    repository_metadata_path = package_root / "repository.json"

    if not package_dir.is_dir():
        raise PackageToolError(f"missing package directory: {package_dir}")
    if not repository_metadata_path.is_file():
        raise PackageToolError(f"missing repository release metadata: {repository_metadata_path}")
    if not is_package_published(package_root):
        raise PackageToolError(
            f"{repository_metadata_path}: package is marked publish=false and cannot be released"
        )

    manifest = load_valid_manifest(package_dir)
    if manifest["id"] != package_id:
        raise PackageToolError(
            f"{package_dir / 'extension.json'}: manifest id {manifest['id']} does not match {package_id}"
        )
    if manifest["version"] != version:
        raise PackageToolError(
            f"{package_dir / 'extension.json'}: manifest version {manifest['version']} does not match {version}"
        )

    repository_metadata = read_json(repository_metadata_path)
    latest_version = repository_metadata.get("latest_version", manifest["version"])
    if latest_version != version:
        raise PackageToolError(
            f"{repository_metadata_path}: latest_version {latest_version} does not match release version {version}"
        )

    releases = repository_metadata.get("releases")
    if not isinstance(releases, list):
        raise PackageToolError(f"{repository_metadata_path}: releases must be an array")

    release = next((item for item in releases if item.get("version") == version), None)
    if release is None:
        raise PackageToolError(f"{repository_metadata_path}: no release entry for version {version}")

    asset_base_url = release.get("asset_base_url")
    if not isinstance(asset_base_url, str) or not asset_base_url:
        raise PackageToolError(
            f"{repository_metadata_path}: release {version} must declare asset_base_url"
        )

    expected_release_tag = f"{package_id}-v{version}"
    expected_asset_base_url = (
        f"https://github.com/{expected_github_repository}/releases/download/"
        f"{expected_release_tag}"
    )
    if asset_base_url.rstrip("/") != expected_asset_base_url:
        raise PackageToolError(
            f"{repository_metadata_path}: release {version} asset_base_url must be "
            f"{expected_asset_base_url}"
        )

    return {
        "package_id": package_id,
        "version": version,
        "manifest_name": manifest["name"],
        "release_tag": expected_release_tag,
        "release_title": f"{manifest['name']} {version}",
        "asset_base_url": asset_base_url,
        "changelog": release.get("changelog", ""),
        "published_at": release.get("published_at", ""),
    }


def _validate_package_id(value):
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
    if (
        not isinstance(value, str)
        or not value
        or value[0] in "-_"
        or any(character not in allowed for character in value)
    ):
        raise PackageToolError(
            "package_id must use lowercase letters, numbers, dashes, or underscores"
        )


def write_github_outputs(path, values):
    with Path(path).open("a", encoding="utf-8", newline="\n") as handle:
        for key, value in values.items():
            text = "" if value is None else str(value)
            if "\n" in text:
                delimiter = f"EOF_{uuid.uuid4().hex}"
                handle.write(f"{key}<<{delimiter}\n{text}\n{delimiter}\n")
            else:
                handle.write(f"{key}={text}\n")


def write_step_summary(path, markdown):
    with Path(path).open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(markdown)
        if not markdown.endswith("\n"):
            handle.write("\n")


def format_available_release_markdown(available):
    lines = [
        "## Available publishable packages",
        "",
        "| Package ID | Name | Latest version | Declared release versions |",
        "| --- | --- | --- | --- |",
    ]

    if not available:
        lines.append("| _none_ | _none_ | _none_ | _none_ |")
    else:
        for item in available:
            versions = ", ".join(f"`{version}`" for version in item["versions"]) or "_none_"
            lines.append(
                "| "
                f"`{item['package_id']}` | "
                f"{item['manifest_name']} | "
                f"`{item['latest_version']}` | "
                f"{versions} |"
            )

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Resolve release metadata for a package release.")
    parser.add_argument("--packages-root", default="packages")
    parser.add_argument("--package-id")
    parser.add_argument("--version")
    parser.add_argument(
        "--expected-github-repository",
        default=os.environ.get("GITHUB_REPOSITORY", OFFICIAL_GITHUB_REPOSITORY),
        help="owner/name repository expected in release.asset_base_url.",
    )
    parser.add_argument(
        "--list-available",
        action="store_true",
        help="List publishable package ids and declared release versions discovered from the repository.",
    )
    parser.add_argument(
        "--github-step-summary",
        action="store_true",
        help="Append the available package/version list to GITHUB_STEP_SUMMARY when used with --list-available.",
    )
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="Append selected values to the GITHUB_OUTPUT file for GitHub Actions.",
    )
    args = parser.parse_args()

    if args.list_available:
        try:
            available = list_available_release_metadata(args.packages_root)
        except PackageToolError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        markdown = format_available_release_markdown(available)
        print(markdown.rstrip())

        if args.github_step_summary:
            summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
            if not summary_path:
                print("error: GITHUB_STEP_SUMMARY is not set", file=sys.stderr)
                return 1
            write_step_summary(summary_path, markdown)

        if not args.package_id and not args.version:
            return 0

    if not args.package_id or not args.version:
        parser.error("--package-id and --version are required unless --list-available is used by itself")

    try:
        metadata = resolve_release_metadata(
            args.packages_root,
            args.package_id,
            args.version,
            expected_github_repository=args.expected_github_repository,
        )
    except PackageToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.github_output:
        output_path = os.environ.get("GITHUB_OUTPUT")
        if not output_path:
            print("error: GITHUB_OUTPUT is not set", file=sys.stderr)
            return 1
        write_github_outputs(
            output_path,
            {
                "package_id": metadata["package_id"],
                "version": metadata["version"],
                "release_tag": metadata["release_tag"],
                "release_title": metadata["release_title"],
                "asset_base_url": metadata["asset_base_url"],
                "changelog": metadata["changelog"],
            },
        )

    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
