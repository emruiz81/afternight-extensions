import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from afternight_repo.package_tools import (  # noqa: E402
    build_package,
    generate_index,
    is_package_published,
    load_valid_manifest,
    read_json,
    sha256_file,
)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class PackageToolTests(unittest.TestCase):
    def setUp(self):
        if shutil.which("zstd") is None:
            self.skipTest("zstd CLI is required for package builder tests")

    def create_package(self, root):
        package_dir = root / "packages" / "example_ext" / "package"
        package_dir.mkdir(parents=True)
        write_json(
            package_dir / "extension.json",
            {
                "id": "example_ext",
                "name": "Example Extension",
                "version": "1.0.0",
                "summary": "Small package fixture.",
                "description": "A deterministic package-builder fixture.",
                "author": "AfterNight Tests",
                "license": "MIT",
                "publisher_id": "afternight.tests",
                "attribution": (
                    "AfterNight port of Example Extension, originally authored by "
                    "Fixture Author."
                ),
                "original_author": "Fixture Author",
                "original_project": "Fixture Suite",
                "original_source_url": "https://example.invalid/upstream/example_ext.py",
                "upstream_commit": "0123456789abcdef",
                "type": "python",
                "entry_point": "example_ext",
                "process_class": "ExampleExtension",
                "category": "filters",
                "launch_mode": "single_image",
                "package_format_version": 1,
                "protocol_version": 1,
                "sdk_version": 1,
                "runtime_targets": ["linux-clang-x86_64"],
                "tags": ["fixture"],
            },
        )
        (package_dir / "example_ext.py").write_text(
            "class ExampleExtension: pass\n", encoding="utf-8"
        )
        (package_dir / "LICENSE").write_text("MIT\n", encoding="utf-8")
        write_json(
            root / "packages" / "example_ext" / "repository.json",
            {
                "releases": [
                    {
                        "version": "1.0.0",
                        "min_app_version": "2.0.0",
                        "changelog": "Initial fixture release.",
                        "published_at": "2026-04-27T00:00:00Z",
                    }
                ]
            },
        )
        return package_dir

    def test_build_package_is_deterministic_tar_zst(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = self.create_package(root)

            first = build_package(package_dir, root / "dist-a", compression_level=3)
            second = build_package(package_dir, root / "dist-b", compression_level=3)

            self.assertEqual(first["package_hash"], second["package_hash"])
            self.assertEqual(
                (root / "dist-a" / first["name"]).read_bytes(),
                (root / "dist-b" / second["name"]).read_bytes(),
            )
            self.assertEqual(first["package_hash"], "sha256:" + sha256_file(root / "dist-a" / first["name"]))

            tar_bytes = subprocess.check_output(
                ["zstd", "-q", "-d", "-c", str(root / "dist-a" / first["name"])]
            )
            tar_path = root / "package.tar"
            tar_path.write_bytes(tar_bytes)
            with tarfile.open(tar_path, "r") as archive:
                names = archive.getnames()
                self.assertEqual(names, sorted(names))
                self.assertIn("example_ext/extension.json", names)
                self.assertIn("example_ext/example_ext.py", names)
                self.assertTrue(all(member.mtime == 0 for member in archive.getmembers()))

    def test_build_package_accepts_long_wheel_filenames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = self.create_package(root)
            wheelhouse = package_dir / "wheelhouse"
            wheelhouse.mkdir()
            long_wheel_name = (
                "nvidia_cuda_runtime_cu12-12.9.79-py3-none-"
                "manylinux2014_x86_64.manylinux_2_17_x86_64.whl"
            )
            (wheelhouse / long_wheel_name).write_text("wheel fixture\n", encoding="utf-8")

            asset = build_package(package_dir, root / "dist", compression_level=3)

            tar_bytes = subprocess.check_output(
                ["zstd", "-q", "-d", "-c", str(root / "dist" / asset["name"])]
            )
            tar_path = root / "package.tar"
            tar_path.write_bytes(tar_bytes)
            with tarfile.open(tar_path, "r") as archive:
                self.assertIn(f"example_ext/wheelhouse/{long_wheel_name}", archive.getnames())

    def test_generate_index_uses_compressed_asset_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = self.create_package(root)
            asset = build_package(package_dir, root / "dist", compression_level=3)

            index = generate_index(
                packages_root=root / "packages",
                assets_dir=root / "dist",
                repository="afternight-extensions",
                updated_at="2026-04-27T00:00:00Z",
                base_url="https://example.invalid/releases",
            )

            self.assertEqual(index["schema_version"], 1)
            self.assertTrue(index["official"])
            self.assertEqual(len(index["extensions"]), 1)
            package = index["extensions"][0]
            self.assertEqual(package["id"], "example_ext")
            self.assertEqual(package["latest_version"], "1.0.0")
            self.assertEqual(
                package["attribution"],
                "AfterNight port of Example Extension, originally authored by Fixture Author.",
            )
            self.assertEqual(package["original_author"], "Fixture Author")
            self.assertEqual(package["original_project"], "Fixture Suite")
            self.assertEqual(
                package["original_source_url"],
                "https://example.invalid/upstream/example_ext.py",
            )
            self.assertEqual(package["upstream_commit"], "0123456789abcdef")
            release = package["releases"][0]
            self.assertEqual(release["runtime_targets"], ["linux-clang-x86_64"])
            self.assertEqual(release["min_app_version"], "2.0.0")
            self.assertEqual(release["assets"][0]["name"], asset["name"])
            self.assertEqual(release["assets"][0]["package_hash"], asset["package_hash"])
            self.assertEqual(
                release["assets"][0]["download_url"],
                "https://example.invalid/releases/" + asset["name"],
            )

    def test_generate_index_allows_release_specific_asset_base_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = self.create_package(root)
            asset = build_package(package_dir, root / "dist", compression_level=3)
            repository_metadata = read_json(package_dir.parent / "repository.json")
            repository_metadata["releases"][0]["asset_base_url"] = (
                "https://example.invalid/releases/example_ext-v1.0.0"
            )
            write_json(package_dir.parent / "repository.json", repository_metadata)

            index = generate_index(
                packages_root=root / "packages",
                assets_dir=root / "dist",
                repository="afternight-extensions",
                updated_at="2026-04-27T00:00:00Z",
                base_url="https://example.invalid/releases/global",
            )

            release = index["extensions"][0]["releases"][0]
            self.assertEqual(
                release["assets"][0]["download_url"],
                "https://example.invalid/releases/example_ext-v1.0.0/" + asset["name"],
            )

    def test_generate_index_skips_unpublished_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = self.create_package(root)
            write_json(package_dir.parent / "repository.json", {"publish": False, "releases": []})

            index = generate_index(
                packages_root=root / "packages",
                assets_dir=root / "dist",
                repository="afternight-extensions",
                updated_at="2026-04-27T00:00:00Z",
            )

            self.assertFalse(is_package_published(package_dir.parent))
            self.assertEqual(index["extensions"], [])


class RepositoryPackageTests(unittest.TestCase):
    def test_repository_packages_have_release_metadata(self):
        package_dirs = sorted((REPO_ROOT / "packages").glob("*/package"))
        self.assertTrue(package_dirs)

        for package_dir in package_dirs:
            with self.subTest(package=package_dir.parent.name):
                manifest = load_valid_manifest(package_dir)
                repository_metadata = read_json(package_dir.parent / "repository.json")
                releases = repository_metadata.get("releases", [])
                versions = {release.get("version") for release in releases}

                self.assertIn(manifest["version"], versions)
                self.assertIn(repository_metadata.get("latest_version", manifest["version"]), versions)

    def test_veralux_package_declares_suite_processes_and_port_provenance(self):
        package_dir = REPO_ROOT / "packages" / "veralux" / "package"
        self.assertTrue(package_dir.is_dir())

        required_fields = (
            "attribution",
            "original_author",
            "original_project",
            "original_source_url",
            "upstream_commit",
        )
        manifest = load_valid_manifest(package_dir)
        self.assertEqual(manifest["id"], "veralux")
        self.assertNotIn("process_class", manifest)
        self.assertEqual(manifest["entry_point"], "veralux_extension")
        self.assertEqual(manifest["dependencies"]["dependency_context"], "private")
        self.assertEqual(len(manifest["processes"]), 8)
        processes = {process["id_suffix"]: process for process in manifest["processes"]}
        self.assertEqual(processes["alchemy"]["class"], "VeraLuxAlchemyExtension")
        self.assertEqual(processes["alchemy"]["category"], "color")
        self.assertEqual(processes["curves"]["class"], "VeraLuxCurvesExtension")
        self.assertEqual(processes["curves"]["category"], "transforms")
        self.assertEqual(
            processes["hypermetric_stretch"]["class"],
            "VeraLuxHyperMetricStretchExtension",
        )
        self.assertEqual(processes["hypermetric_stretch"]["category"], "transforms")
        self.assertEqual(processes["nox"]["class"], "VeraLuxNoxExtension")
        self.assertEqual(processes["nox"]["category"], "background_extraction")
        self.assertEqual(processes["starcomposer"]["class"], "VeraLuxStarComposerExtension")
        self.assertEqual(processes["starcomposer"]["category"], "star_object")
        self.assertEqual(processes["vectra"]["class"], "VeraLuxVectraExtension")
        self.assertEqual(processes["vectra"]["category"], "color")
        self.assertEqual(processes["revela"]["class"], "VeraLuxRevelaExtension")
        self.assertEqual(processes["revela"]["category"], "sharpening_enhancement")
        self.assertEqual(processes["silentium"]["class"], "VeraLuxSilentiumExtension")
        self.assertEqual(processes["silentium"]["category"], "denoising")

        for field in required_fields:
            self.assertTrue(manifest.get(field), f"{field} is required")
        self.assertEqual(manifest["original_author"], "Riccardo Paterniti")
        self.assertEqual(manifest["original_project"], "VeraLux")
        self.assertTrue((package_dir / "UPSTREAM.md").is_file())
        quality_notes = (package_dir / "QUALITY_VALIDATION.md").read_text(encoding="utf-8")
        self.assertIn("Automated Upstream Checks", quality_notes)
        self.assertIn("Alchemy", quality_notes)
        self.assertIn("HyperMetric Stretch", quality_notes)
        self.assertIn("First-Pass Intentional Divergences", quality_notes)
        upstream = read_json(package_dir / "UPSTREAM.json")
        self.assertEqual(
            sorted(source["tool"] for source in upstream["sources"]),
            [
                "Alchemy",
                "Curves",
                "HyperMetric Stretch",
                "Nox",
                "Revela",
                "Silentium",
                "StarComposer",
                "Starting Point",
                "Vectra",
            ],
        )

    def test_veralux_publication_readiness_keeps_visual_qa_gate_closed(self):
        package_root = REPO_ROOT / "packages" / "veralux"
        repository_metadata = read_json(package_root / "repository.json")
        readiness = (package_root / "packaging" / "PUBLICATION_READINESS.md").read_text(
            encoding="utf-8"
        )
        packaging_notes = (package_root / "packaging" / "README.md").read_text(encoding="utf-8")

        self.assertFalse(repository_metadata.get("publish", True))
        self.assertIn("Status: source-staged, not publishable yet.", readiness)
        self.assertIn('"publish": false', readiness)
        self.assertIn("Representative real-image visual QA and release signoff", readiness)
        self.assertIn("- [ ] Representative real-image visual QA", readiness)
        self.assertIn("PUBLICATION_READINESS.md", packaging_notes)
        self.assertIn("visual QA signoff", packaging_notes)

    def test_veralux_package_asset_smoke_contains_one_suite_and_all_processes(self):
        if shutil.which("zstd") is None:
            self.skipTest("zstd CLI is required for VeraLux package smoke test")

        package_dir = REPO_ROOT / "packages" / "veralux" / "package"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = build_package(package_dir, root / "dist", compression_level=3)

            self.assertEqual(asset["package_id"], "veralux")
            self.assertEqual(asset["name"], "veralux-0.1.0-all.tar.zst")
            self.assertEqual(
                asset["runtime_targets"],
                ["linux-clang-x86_64", "windows-msvc-x86_64"],
            )

            tar_bytes = subprocess.check_output(
                ["zstd", "-q", "-d", "-c", str(root / "dist" / asset["name"])]
            )
            tar_path = root / "veralux-package.tar"
            tar_path.write_bytes(tar_bytes)

            with tarfile.open(tar_path, "r") as archive:
                names = archive.getnames()
                self.assertTrue(
                    all(name == "veralux" or name.startswith("veralux/") for name in names)
                )
                self.assertIn("veralux/extension.json", names)
                self.assertIn("veralux/requirements.lock", names)
                self.assertIn("veralux/STARTING_POINT.md", names)
                self.assertIn("veralux/UPSTREAM.json", names)
                self.assertIn("veralux/QUALITY_VALIDATION.md", names)
                self.assertIn("veralux/THIRD_PARTY_NOTICES.md", names)

                for split_root in (
                    "veralux_revela",
                    "veralux_alchemy",
                    "veralux_hypermetric_stretch",
                    "veralux_vectra",
                    "veralux_starcomposer",
                    "veralux_curves",
                    "veralux_silentium",
                    "veralux_nox",
                ):
                    self.assertNotIn(split_root, names)
                    self.assertFalse(any(name.startswith(split_root + "/") for name in names))

                manifest_member = archive.extractfile("veralux/extension.json")
                self.assertIsNotNone(manifest_member)
                manifest = json.loads(manifest_member.read().decode("utf-8"))

        self.assertEqual(manifest["id"], "veralux")
        self.assertEqual(manifest["entry_point"], "veralux_extension")
        self.assertNotIn("process_class", manifest)
        self.assertEqual(manifest["dependencies"]["dependency_context"], "private")
        self.assertEqual(manifest["dependencies"]["requirements_file"], "requirements.lock")
        self.assertTrue(manifest["dependencies"]["pip"]["require_hashes"])
        self.assertEqual(
            sorted(process["id_suffix"] for process in manifest["processes"]),
            [
                "alchemy",
                "curves",
                "hypermetric_stretch",
                "nox",
                "revela",
                "silentium",
                "starcomposer",
                "vectra",
            ],
        )

    def test_veralux_starting_point_guide_documents_workflow_order(self):
        package_dir = REPO_ROOT / "packages" / "veralux" / "package"
        guide_path = package_dir / "STARTING_POINT.md"
        self.assertTrue(guide_path.is_file())

        guide = guide_path.read_text(encoding="utf-8")
        self.assertIn("AfterNight adaptation of VeraLux Starting Point", guide)
        self.assertIn("Starting Point is not registered as a processing process", guide)
        self.assertIn("VeraLux Nox", guide)
        self.assertIn("VeraLux Silentium", guide)
        self.assertIn("VeraLux Alchemy", guide)
        self.assertIn("VeraLux HyperMetric Stretch", guide)
        self.assertIn("VeraLux Curves", guide)
        self.assertIn("VeraLux Revela", guide)
        self.assertIn("VeraLux Vectra", guide)
        self.assertIn("VeraLux StarComposer", guide)
        self.assertLess(guide.index("VeraLux Nox"), guide.index("VeraLux Silentium"))
        self.assertLess(guide.index("VeraLux Silentium"), guide.index("VeraLux Alchemy"))
        self.assertLess(guide.index("VeraLux Alchemy"), guide.index("VeraLux HyperMetric Stretch"))
        self.assertLess(guide.index("VeraLux HyperMetric Stretch"), guide.index("VeraLux Curves"))
        self.assertLess(guide.index("VeraLux Curves"), guide.index("VeraLux Revela"))
        self.assertLess(guide.index("VeraLux Revela"), guide.index("VeraLux Vectra"))
        self.assertLess(guide.index("VeraLux Vectra"), guide.index("VeraLux StarComposer"))


if __name__ == "__main__":
    unittest.main()
