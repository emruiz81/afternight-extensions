# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Ezequiel Ruiz

import hashlib
import json
import re
import subprocess
from pathlib import Path


class VeraLuxUpstreamError(RuntimeError):
    """Raised when the VeraLux upstream checker cannot inspect the requested ref."""


def _git_output(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise VeraLuxUpstreamError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def _git_bytes(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise VeraLuxUpstreamError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def _read_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _extract_version(source):
    text = source.decode("utf-8", errors="replace")
    match = re.search(r"^\s*VERSION\s*=\s*[\"']([^\"']+)[\"']", text, re.MULTILINE)
    return match.group(1) if match else ""


def _source_at_ref(upstream_checkout, ref, original_path):
    return _git_bytes(upstream_checkout, "show", f"{ref}:{original_path}")


def _last_commit_at_ref(upstream_checkout, ref, original_path):
    return _git_output(upstream_checkout, "log", "-1", "--format=%H", ref, "--", original_path)


def check_veralux_upstream(package_dir, upstream_checkout, ref=None):
    """Compare VeraLux UPSTREAM.json entries against a local upstream git checkout."""

    package_dir = Path(package_dir)
    upstream_checkout = Path(upstream_checkout)
    manifest_path = package_dir / "UPSTREAM.json"
    manifest = _read_json(manifest_path)
    selected_ref = ref or manifest.get("upstream_commit")
    if not selected_ref:
        raise VeraLuxUpstreamError(f"{manifest_path}: upstream_commit is required when ref is omitted")

    resolved_ref = _git_output(upstream_checkout, "rev-parse", selected_ref)
    report = {
        "success": True,
        "package_dir": str(package_dir),
        "upstream_checkout": str(upstream_checkout),
        "manifest_upstream_commit": manifest.get("upstream_commit", ""),
        "ref": selected_ref,
        "resolved_ref": resolved_ref,
        "sources": [],
    }

    for source in manifest.get("sources", []):
        tool = source.get("tool", "")
        original_path = source.get("original_path", "")
        entry = {
            "tool": tool,
            "original_path": original_path,
            "status": "ok",
            "issues": [],
            "expected_sha256": source.get("original_file_sha256", ""),
            "expected_last_commit": source.get("original_file_last_commit", ""),
            "expected_version": source.get("original_version", ""),
            "actual_sha256": "",
            "actual_last_commit": "",
            "actual_version": "",
        }

        try:
            data = _source_at_ref(upstream_checkout, selected_ref, original_path)
            entry["actual_sha256"] = _sha256_bytes(data)
            entry["actual_last_commit"] = _last_commit_at_ref(upstream_checkout, selected_ref, original_path)
            entry["actual_version"] = _extract_version(data)
        except VeraLuxUpstreamError as exc:
            entry["issues"].append(str(exc))

        if entry["expected_sha256"] != entry["actual_sha256"]:
            entry["issues"].append("sha256 mismatch")
        if entry["expected_last_commit"] != entry["actual_last_commit"]:
            entry["issues"].append("last commit mismatch")
        if entry["expected_version"] != entry["actual_version"]:
            entry["issues"].append("version mismatch")

        if entry["issues"]:
            entry["status"] = "changed"
            report["success"] = False
        report["sources"].append(entry)

    return report


def format_veralux_upstream_report(report):
    lines = [
        f"VeraLux upstream check: {report['ref']} ({report['resolved_ref']})",
        f"Package: {report['package_dir']}",
        f"Upstream checkout: {report['upstream_checkout']}",
    ]
    for source in report["sources"]:
        prefix = "OK" if source["status"] == "ok" else "CHANGED"
        lines.append(f"{prefix}: {source['tool']} [{source['original_path']}]")
        if source["status"] != "ok":
            lines.append(f"  issues: {', '.join(source['issues'])}")
            lines.append(f"  sha256: {source['expected_sha256']} -> {source['actual_sha256']}")
            lines.append(f"  last_commit: {source['expected_last_commit']} -> {source['actual_last_commit']}")
            lines.append(f"  version: {source['expected_version']} -> {source['actual_version']}")
    lines.append("Result: OK" if report["success"] else "Result: changes detected")
    return "\n".join(lines)
