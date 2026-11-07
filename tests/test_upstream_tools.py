# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Ezequiel Ruiz

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from afternight_repo.upstream import check_upstream, find_upstream_packages  # noqa: E402


CHECK_UPSTREAM = REPO_ROOT / "tools" / "check_upstream.py"


def run_git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def git_output(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


class UpstreamToolTests(unittest.TestCase):
    FILES = {
        "processing/Upper.py": b'VERSION = "1.2.6"\nprint("upper")\n',
        "processing/Lower.py": b'version = "v3.0.7"\nprint("lower")\n',
    }

    def setUp(self):
        if shutil.which("git") is None:
            self.skipTest("git CLI is required for upstream checker tests")

    def create_fixture(self, root):
        upstream = root / "upstream"
        upstream.mkdir(parents=True)
        run_git(upstream, "init")
        run_git(upstream, "config", "user.email", "tests@example.invalid")
        run_git(upstream, "config", "user.name", "AfterNight Tests")
        for relative, data in self.FILES.items():
            path = upstream / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        run_git(upstream, "add", "processing")
        run_git(upstream, "commit", "-m", "fixture baseline")
        baseline = git_output(upstream, "rev-parse", "HEAD")

        packages_root = root / "packages"
        sources = {
            "upper_port": {
                "tool": "Upper",
                "original_path": "processing/Upper.py",
                "original_file_sha256": sha256_bytes(self.FILES["processing/Upper.py"]),
                "original_file_last_commit": baseline,
                "original_version": "1.2.6",
            },
            "lower_port": {
                "tool": "Lower",
                "original_path": "processing/Lower.py",
                "original_file_sha256": sha256_bytes(self.FILES["processing/Lower.py"]),
                "original_file_last_commit": baseline,
                "original_version": "v3.0.7",
                "version_constant": "version",
            },
        }
        for package_id, source in sources.items():
            package = packages_root / package_id / "package"
            package.mkdir(parents=True)
            manifest = {"upstream_commit": baseline, "sources": [source]}
            (package / "UPSTREAM.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (packages_root / "no_upstream" / "package").mkdir(parents=True)
        return upstream, packages_root, baseline

    def test_version_constant_selects_the_assignment_read_as_the_version(self):
        with tempfile.TemporaryDirectory() as temp:
            upstream, packages_root, _baseline = self.create_fixture(Path(temp))

            lower = check_upstream(packages_root / "lower_port" / "package", upstream)
            upper = check_upstream(packages_root / "upper_port" / "package", upstream)

            self.assertTrue(lower["success"], lower)
            self.assertEqual(lower["sources"][0]["actual_version"], "v3.0.7")
            self.assertTrue(upper["success"], upper)
            self.assertEqual(upper["sources"][0]["actual_version"], "1.2.6")

    def test_find_upstream_packages_lists_only_packages_with_upstream_json(self):
        with tempfile.TemporaryDirectory() as temp:
            _upstream, packages_root, _baseline = self.create_fixture(Path(temp))

            found = [path.parent.name for path in find_upstream_packages(packages_root)]

            self.assertEqual(found, ["lower_port", "upper_port"])

    def test_cli_checks_every_upstream_package_and_reports_a_change(self):
        with tempfile.TemporaryDirectory() as temp:
            upstream, packages_root, _baseline = self.create_fixture(Path(temp))
            command = [
                sys.executable,
                str(CHECK_UPSTREAM),
                "--packages-root",
                str(packages_root),
                "--upstream-checkout",
                str(upstream),
                "--json",
            ]

            clean = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertEqual(len(json.loads(clean.stdout)), 2)

            (upstream / "processing" / "Lower.py").write_text('version = "v3.0.8"\n', encoding="utf-8")
            run_git(upstream, "commit", "-am", "change lower")

            changed = subprocess.run([*command, "--ref", "HEAD"], check=False, capture_output=True, text=True)
            self.assertEqual(changed.returncode, 2, changed.stderr)
            reports = {report["sources"][0]["tool"]: report for report in json.loads(changed.stdout)}
            self.assertFalse(reports["Lower"]["success"])
            self.assertEqual(reports["Lower"]["sources"][0]["actual_version"], "v3.0.8")
            self.assertTrue(reports["Upper"]["success"])


if __name__ == "__main__":
    unittest.main()
