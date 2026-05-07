# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Ezequiel Ruiz

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from afternight_repo.veralux_upstream import check_veralux_upstream  # noqa: E402


def run_git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def git_output(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def sha256_bytes(data):
    import hashlib

    return hashlib.sha256(data).hexdigest()


class VeraLuxUpstreamToolTests(unittest.TestCase):
    def setUp(self):
        if shutil.which("git") is None:
            self.skipTest("git CLI is required for VeraLux upstream checker tests")

    def create_fixture(self, root):
        upstream = root / "upstream"
        package = root / "packages" / "veralux" / "package"
        upstream.mkdir(parents=True)
        package.mkdir(parents=True)
        run_git(upstream, "init")
        run_git(upstream, "config", "user.email", "tests@example.invalid")
        run_git(upstream, "config", "user.name", "AfterNight Tests")

        files = {
            "VeraLux/VeraLux_Revela.py": b'VERSION = "1.0.2"\nprint("revela")\n',
            "VeraLux/VeraLux_Starting_Point.py": b'VERSION = "1.0.0"\nprint("guide")\n',
        }
        for relative, data in files.items():
            path = upstream / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        run_git(upstream, "add", "VeraLux")
        run_git(upstream, "commit", "-m", "fixture baseline")
        baseline = git_output(upstream, "rev-parse", "HEAD")

        manifest = {
            "upstream_repo_url": "https://example.invalid/siril-scripts.git",
            "upstream_commit": baseline,
            "sources": [
                {
                    "tool": "Revela",
                    "original_path": "VeraLux/VeraLux_Revela.py",
                    "original_file_sha256": sha256_bytes(files["VeraLux/VeraLux_Revela.py"]),
                    "original_file_last_commit": baseline,
                    "original_version": "1.0.2",
                },
                {
                    "tool": "Starting Point",
                    "original_path": "VeraLux/VeraLux_Starting_Point.py",
                    "original_file_sha256": sha256_bytes(files["VeraLux/VeraLux_Starting_Point.py"]),
                    "original_file_last_commit": baseline,
                    "original_version": "1.0.0",
                },
            ],
        }
        (package / "UPSTREAM.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return upstream, package, baseline

    def test_check_veralux_upstream_matches_pinned_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            upstream, package, baseline = self.create_fixture(Path(temp))

            report = check_veralux_upstream(package, upstream, ref=baseline)

            self.assertTrue(report["success"])
            self.assertEqual(report["ref"], baseline)
            self.assertEqual([source["tool"] for source in report["sources"]], ["Revela", "Starting Point"])
            self.assertTrue(all(source["status"] == "ok" for source in report["sources"]))

    def test_check_veralux_upstream_reports_changed_source_ref(self):
        with tempfile.TemporaryDirectory() as temp:
            upstream, package, _baseline = self.create_fixture(Path(temp))
            changed_path = upstream / "VeraLux" / "VeraLux_Revela.py"
            changed_path.write_text('VERSION = "1.0.3"\nprint("revela changed")\n', encoding="utf-8")
            run_git(upstream, "add", "VeraLux/VeraLux_Revela.py")
            run_git(upstream, "commit", "-m", "change revela")

            report = check_veralux_upstream(package, upstream, ref="HEAD")
            changed = {source["tool"]: source for source in report["sources"]}

            self.assertFalse(report["success"])
            self.assertEqual(changed["Revela"]["status"], "changed")
            self.assertIn("sha256 mismatch", changed["Revela"]["issues"])
            self.assertIn("last commit mismatch", changed["Revela"]["issues"])
            self.assertIn("version mismatch", changed["Revela"]["issues"])
            self.assertEqual(changed["Revela"]["actual_version"], "1.0.3")
            self.assertEqual(changed["Starting Point"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
