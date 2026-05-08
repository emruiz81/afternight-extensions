# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Ezequiel Ruiz

import json
import os
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
    PackageToolError,
    build_package,
    generate_index,
    is_package_published,
    load_valid_manifest,
    read_json,
    sha256_file,
)
from afternight_repo.signing import (  # noqa: E402
    SIGNATURE_ALGORITHM,
    canonical_asset_signature_payload,
    signed_metadata,
    signing_payload_for_metadata,
    verify_payload_signature,
)
from release_metadata import (  # noqa: E402
    list_available_release_metadata,
    resolve_release_metadata,
)
from update_live_index import update_live_index  # noqa: E402


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def create_policy_package(root, *, license_id="MIT", sdk_backend="protocol", source_text=None, capabilities=None):
    package_dir = root / "package"
    package_dir.mkdir(parents=True)
    manifest = {
        "id": "policy_ext",
        "name": "Policy Extension",
        "version": "1.0.0",
        "summary": "Policy fixture.",
        "description": "A host-mode policy fixture.",
        "author": "AfterNight Tests",
        "license": license_id,
        "publisher_id": "afternight.tests",
        "type": "python",
        "entry_point": "policy_ext",
        "process_class": "PolicyExtension",
        "category": "filters",
        "launch_mode": "single_image",
        "sdk_backend": sdk_backend,
        "package_format_version": 1,
        "protocol_version": 1,
        "sdk_version": 1,
    }
    if capabilities is not None:
        manifest["capabilities"] = capabilities
    write_json(package_dir / "extension.json", manifest)
    (package_dir / "policy_ext.py").write_text(
        source_text or "from afternight import views\n\nclass PolicyExtension: pass\n",
        encoding="utf-8",
    )
    (package_dir / "LICENSE").write_text(license_id + "\n", encoding="utf-8")
    return package_dir


TEST_SIGNING_KEY_ID = "afternight-test-ed25519-v1"
TEST_SIGNING_SEED_B64 = "nWGxne/9WmC6hEr0kuwsxERJxWl7MmkZcDusAxyuf2A="
TEST_SIGNING_PUBLIC_KEY_B64 = "11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo="


class SigningToolTests(unittest.TestCase):
    def test_canonical_payload_is_stable_and_sorts_runtime_targets(self):
        payload = canonical_asset_signature_payload(
            package_id="example_ext",
            version="1.0.0",
            asset_name="example_ext-1.0.0-all.tar.zst",
            package_hash="SHA256:" + ("A" * 64),
            runtime_targets=["windows-msvc-x86_64", "linux-clang-x86_64"],
            signature_key_id=TEST_SIGNING_KEY_ID,
        )

        self.assertEqual(
            payload.decode("utf-8"),
            "\n".join(
                (
                    "afternight-extension-asset-signature-v1",
                    "package_id=example_ext",
                    "version=1.0.0",
                    "asset_name=example_ext-1.0.0-all.tar.zst",
                    "package_hash=sha256:" + ("a" * 64),
                    "runtime_targets=linux-clang-x86_64,windows-msvc-x86_64",
                    "signature_algorithm=ed25519",
                    f"signature_key_id={TEST_SIGNING_KEY_ID}",
                )
            ),
        )

    def test_canonical_payload_rejects_newline_fields(self):
        with self.assertRaisesRegex(RuntimeError, "must not contain newlines"):
            canonical_asset_signature_payload(
                package_id="example_ext\nbad",
                version="1.0.0",
                asset_name="example_ext-1.0.0-all.tar.zst",
                package_hash="sha256:" + ("a" * 64),
                runtime_targets=["linux-clang-x86_64"],
                signature_key_id=TEST_SIGNING_KEY_ID,
            )

    def test_sign_repository_assets_updates_metadata_and_emits_signature_sidecar(self):
        if shutil.which("zstd") is None:
            self.skipTest("zstd CLI is required for package builder tests")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = PackageToolTests().create_package(root)
            asset = build_package(package_dir, root / "dist", compression_level=3)
            keys_path = root / "public_keys.json"
            write_json(
                keys_path,
                {
                    "keys": [
                        {
                            "key_id": TEST_SIGNING_KEY_ID,
                            "algorithm": "ed25519",
                            "public_key_base64": TEST_SIGNING_PUBLIC_KEY_B64,
                        }
                    ]
                },
            )

            env = os.environ.copy()
            env["AFTERNIGHT_EXTENSION_SIGNING_KEY_ED25519_SEED_B64"] = TEST_SIGNING_SEED_B64
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "tools" / "sign_repository_assets.py"),
                    "--assets-dir",
                    str(root / "dist"),
                    "--package-id",
                    "example_ext",
                    "--version",
                    "1.0.0",
                    "--key-id",
                    TEST_SIGNING_KEY_ID,
                    "--public-keys",
                    str(keys_path),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            signed = read_json(root / "dist" / f"{asset['name']}.metadata.json")
            self.assertEqual(signed["signature_state"], "verified")
            self.assertEqual(signed["signature_algorithm"], SIGNATURE_ALGORITHM)
            self.assertEqual(signed["signature_key_id"], TEST_SIGNING_KEY_ID)
            self.assertTrue((root / "dist" / f"{asset['name']}.sig").is_file())
            payload = signing_payload_for_metadata(signed, TEST_SIGNING_KEY_ID)
            self.assertTrue(verify_payload_signature(payload, TEST_SIGNING_PUBLIC_KEY_B64, signed["signature"]))


class ManifestHostModePolicyTests(unittest.TestCase):
    def test_protocol_backend_allows_non_gpl_package_without_engine_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = create_policy_package(
                Path(tmp),
                license_id="MIT",
                sdk_backend="protocol",
                source_text="import afternight.ui_protocol as ui\n\nclass PolicyExtension: pass\n",
            )

            manifest = load_valid_manifest(package_dir)

            self.assertEqual(manifest["sdk_backend"], "protocol")
            self.assertEqual(manifest["license"], "MIT")

    def test_manifest_requires_explicit_sdk_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = create_policy_package(Path(tmp))
            manifest = read_json(package_dir / "extension.json")
            del manifest["sdk_backend"]
            write_json(package_dir / "extension.json", manifest)

            with self.assertRaisesRegex(PackageToolError, "sdk_backend must be a non-empty string"):
                load_valid_manifest(package_dir)

    def test_runtime_backend_rejects_non_gpl_license(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = create_policy_package(Path(tmp), license_id="MIT", sdk_backend="runtime")

            with self.assertRaisesRegex(PackageToolError, "runtime packages must use"):
                load_valid_manifest(package_dir)

    def test_runtime_backend_accepts_gpl_license(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = create_policy_package(
                Path(tmp),
                license_id="GPL-3.0-or-later",
                sdk_backend="runtime",
                source_text="from afternight import io\n\nclass PolicyExtension: pass\n",
            )

            manifest = load_valid_manifest(package_dir)

            self.assertEqual(manifest["sdk_backend"], "runtime")

    def test_protocol_backend_rejects_engine_backed_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = create_policy_package(
                Path(tmp),
                sdk_backend="protocol",
                source_text="from afternight import registration\n\nclass PolicyExtension: pass\n",
            )

            with self.assertRaisesRegex(PackageToolError, "Engine-backed module afternight.registration"):
                load_valid_manifest(package_dir)

    def test_protocol_backend_rejects_runtime_module_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = create_policy_package(
                Path(tmp),
                sdk_backend="protocol",
                source_text="import _afternight_runtime\n\nclass PolicyExtension: pass\n",
            )

            with self.assertRaisesRegex(PackageToolError, "Engine-backed module _afternight_runtime"):
                load_valid_manifest(package_dir)

    def test_protocol_backend_rejects_native_ui_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = create_policy_package(
                Path(tmp),
                sdk_backend="protocol",
                source_text="import afternight.ui as ui\n\nclass PolicyExtension: pass\n",
            )

            with self.assertRaisesRegex(PackageToolError, "native afternight.ui surface afternight.ui"):
                load_valid_manifest(package_dir)

    def test_protocol_backend_rejects_native_control_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = create_policy_package(
                Path(tmp),
                sdk_backend="protocol",
                capabilities={"native_process_window": True},
            )

            with self.assertRaisesRegex(PackageToolError, "native-control capability"):
                load_valid_manifest(package_dir)

    def test_rpc_backend_is_reserved_until_supported_by_afternight(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = create_policy_package(
                Path(tmp),
                license_id="Apache-2.0",
                sdk_backend="rpc",
            )

            with self.assertRaisesRegex(PackageToolError, "rpc is reserved"):
                load_valid_manifest(package_dir)

    def test_dependencies_require_hash_locked_requirements_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = create_policy_package(Path(tmp))
            manifest = read_json(package_dir / "extension.json")
            manifest["dependencies"] = {
                "dependency_context": "private",
                "requirements_file": "requirements.lock",
                "pip": {
                    "require_hashes": True,
                    "index_urls": ["https://pypi.org/simple"],
                },
            }
            write_json(package_dir / "extension.json", manifest)
            (package_dir / "THIRD_PARTY_NOTICES.md").write_text(
                "Dependency notices.\n", encoding="utf-8"
            )
            (package_dir / "requirements.lock").write_text(
                "example-dependency==1.0.0\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(PackageToolError, "at least one --hash=sha256"):
                load_valid_manifest(package_dir)

    def test_dependencies_accept_hash_locked_requirements_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = create_policy_package(Path(tmp))
            manifest = read_json(package_dir / "extension.json")
            manifest["dependencies"] = {
                "dependency_context": "private",
                "requirements_file": "requirements.lock",
                "pip": {
                    "require_hashes": True,
                    "index_urls": ["https://pypi.org/simple"],
                },
            }
            write_json(package_dir / "extension.json", manifest)
            (package_dir / "THIRD_PARTY_NOTICES.md").write_text(
                "Dependency notices.\n", encoding="utf-8"
            )
            (package_dir / "requirements.lock").write_text(
                "example-dependency==1.0.0 --hash=sha256:" + ("a" * 64) + "\n",
                encoding="utf-8",
            )

            loaded = load_valid_manifest(package_dir)

            self.assertEqual(loaded["dependencies"]["requirements_file"], "requirements.lock")

    def test_dependencies_reject_package_external_find_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = create_policy_package(Path(tmp))
            manifest = read_json(package_dir / "extension.json")
            manifest["dependencies"] = {
                "dependency_context": "private",
                "requirements_file": "requirements.lock",
                "pip": {
                    "require_hashes": True,
                    "find_links": ["../wheelhouse"],
                },
            }
            write_json(package_dir / "extension.json", manifest)
            (package_dir / "THIRD_PARTY_NOTICES.md").write_text(
                "Dependency notices.\n", encoding="utf-8"
            )
            (package_dir / "requirements.lock").write_text(
                "example-dependency==1.0.0 --hash=sha256:" + ("a" * 64) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(PackageToolError, "safe package-local path"):
                load_valid_manifest(package_dir)


class LiveIndexUpdateTests(unittest.TestCase):
    def make_index(self, updated_at, package_versions):
        return {
            "schema_version": 1,
            "repository": "afternight-extensions",
            "official": True,
            "updated_at": updated_at,
            "extensions": [
                {
                    "id": package_id,
                    "name": package_id,
                    "summary": f"{package_id} summary",
                    "description": f"{package_id} description",
                    "author": "AfterNight Tests",
                    "license": "MIT",
                    "latest_version": version,
                    "releases": [
                        {
                            "version": version,
                            "assets": [
                                {
                                    "name": f"{package_id}-{version}.tar.zst",
                                    "download_url": f"https://example.invalid/{package_id}-{version}.tar.zst",
                                    "package_hash": "sha256:" + ("a" * 64),
                                }
                            ],
                        }
                    ],
                }
                for package_id, version in package_versions
            ],
        }

    def test_update_live_index_seeds_selected_package_without_existing_live_index(self):
        candidate = self.make_index("2026-05-07T00:00:00Z", [("alpha", "1.0.0"), ("beta", "2.0.0")])

        live = update_live_index(candidate, "alpha")

        self.assertEqual([package["id"] for package in live["extensions"]], ["alpha"])
        self.assertEqual(live["updated_at"], "2026-05-07T00:00:00Z")

    def test_update_live_index_replaces_only_selected_package(self):
        current = self.make_index("2026-05-01T00:00:00Z", [("alpha", "0.9.0"), ("beta", "1.9.0")])
        candidate = self.make_index("2026-05-07T00:00:00Z", [("alpha", "1.0.0"), ("beta", "2.0.0")])

        live = update_live_index(candidate, "alpha", current)
        live_versions = {package["id"]: package["latest_version"] for package in live["extensions"]}

        self.assertEqual(live_versions, {"alpha": "1.0.0", "beta": "1.9.0"})
        self.assertEqual(live["updated_at"], "2026-05-07T00:00:00Z")

    def test_update_live_index_rejects_missing_selected_package(self):
        candidate = self.make_index("2026-05-07T00:00:00Z", [("alpha", "1.0.0")])

        with self.assertRaisesRegex(ValueError, "does not contain package beta"):
            update_live_index(candidate, "beta")


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
                "sdk_backend": "protocol",
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
            self.assertEqual(release["sdk_backend"], "protocol")
            self.assertEqual(release["assets"][0]["name"], asset["name"])
            self.assertEqual(release["assets"][0]["package_hash"], asset["package_hash"])
            self.assertEqual(
                release["assets"][0]["download_url"],
                "https://example.invalid/releases/" + asset["name"],
            )

    def test_generate_index_uses_signed_asset_sidecar_signature_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = self.create_package(root)
            asset = build_package(package_dir, root / "dist", compression_level=3)
            metadata_path = root / "dist" / f"{asset['name']}.metadata.json"
            metadata = read_json(metadata_path)
            metadata = signed_metadata(
                metadata,
                signature_key_id=TEST_SIGNING_KEY_ID,
                seed_base64=TEST_SIGNING_SEED_B64,
                public_key_base64=TEST_SIGNING_PUBLIC_KEY_B64,
            )
            write_json(metadata_path, metadata)

            index = generate_index(
                packages_root=root / "packages",
                assets_dir=root / "dist",
                repository="afternight-extensions",
                updated_at="2026-04-27T00:00:00Z",
                base_url="https://example.invalid/releases",
            )

            signed_asset = index["extensions"][0]["releases"][0]["assets"][0]
            self.assertEqual(signed_asset["signature_state"], "verified")
            self.assertEqual(signed_asset["signature_algorithm"], SIGNATURE_ALGORITHM)
            self.assertEqual(signed_asset["signature_key_id"], TEST_SIGNING_KEY_ID)
            self.assertEqual(signed_asset["signature"], metadata["signature"])
            self.assertIn("Verified official AfterNight", signed_asset["signature_detail"])

    def test_generate_index_rejects_verified_release_metadata_without_signed_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = self.create_package(root)
            build_package(package_dir, root / "dist", compression_level=3)
            repository_metadata = read_json(package_dir.parent / "repository.json")
            repository_metadata["releases"][0]["signature_state"] = "verified"
            write_json(package_dir.parent / "repository.json", repository_metadata)

            with self.assertRaisesRegex(PackageToolError, "must not declare signature_state verified"):
                generate_index(
                    packages_root=root / "packages",
                    assets_dir=root / "dist",
                    repository="afternight-extensions",
                    updated_at="2026-04-27T00:00:00Z",
                )

    def test_generate_index_rejects_malformed_signature_sidecars(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = self.create_package(root)
            asset = build_package(package_dir, root / "dist", compression_level=3)
            metadata_path = root / "dist" / f"{asset['name']}.metadata.json"
            metadata = read_json(metadata_path)
            metadata["signature_state"] = "unsigned"
            metadata["signature"] = "not allowed"
            write_json(metadata_path, metadata)

            with self.assertRaisesRegex(PackageToolError, "must not declare generated signature field signature"):
                generate_index(
                    packages_root=root / "packages",
                    assets_dir=root / "dist",
                    repository="afternight-extensions",
                    updated_at="2026-04-27T00:00:00Z",
                )

            metadata.pop("signature")
            metadata["signature_state"] = "verified"
            metadata["signature_algorithm"] = SIGNATURE_ALGORITHM
            metadata["signature_key_id"] = TEST_SIGNING_KEY_ID
            metadata["signature_detail"] = "verified fixture"
            write_json(metadata_path, metadata)

            with self.assertRaisesRegex(PackageToolError, "verified assets must declare signature"):
                generate_index(
                    packages_root=root / "packages",
                    assets_dir=root / "dist",
                    repository="afternight-extensions",
                    updated_at="2026-04-27T00:00:00Z",
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

    def test_generate_index_rejects_historical_release_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = self.create_package(root)
            build_package(package_dir, root / "dist", compression_level=3)
            repository_metadata = read_json(package_dir.parent / "repository.json")
            repository_metadata["releases"].append(
                {
                    "version": "0.9.0",
                    "min_app_version": "2.0.0",
                    "changelog": "Older fixture release.",
                    "published_at": "2026-04-01T00:00:00Z",
                }
            )
            write_json(package_dir.parent / "repository.json", repository_metadata)

            with self.assertRaisesRegex(PackageToolError, "current package version only"):
                generate_index(
                    packages_root=root / "packages",
                    assets_dir=root / "dist",
                    repository="afternight-extensions",
                    updated_at="2026-04-27T00:00:00Z",
                )

    def test_release_metadata_accepts_expected_repository_asset_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = self.create_package(root)
            repository_metadata = read_json(package_dir.parent / "repository.json")
            repository_metadata["latest_version"] = "1.0.0"
            repository_metadata["releases"][0]["asset_base_url"] = (
                "https://github.com/acme/extensions/releases/download/example_ext-v1.0.0"
            )
            write_json(package_dir.parent / "repository.json", repository_metadata)

            metadata = resolve_release_metadata(
                root / "packages",
                "example_ext",
                "1.0.0",
                expected_github_repository="acme/extensions",
            )

            self.assertEqual(metadata["release_tag"], "example_ext-v1.0.0")

    def test_release_metadata_rejects_wrong_repository_asset_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = self.create_package(root)
            repository_metadata = read_json(package_dir.parent / "repository.json")
            repository_metadata["latest_version"] = "1.0.0"
            repository_metadata["releases"][0]["asset_base_url"] = (
                "https://github.com/example/wrong/releases/download/example_ext-v1.0.0"
            )
            write_json(package_dir.parent / "repository.json", repository_metadata)

            with self.assertRaisesRegex(PackageToolError, "asset_base_url must be"):
                resolve_release_metadata(root / "packages", "example_ext", "1.0.0")


class RepositoryPackageTests(unittest.TestCase):
    def test_repository_packages_have_release_metadata(self):
        package_dirs = sorted((REPO_ROOT / "packages").glob("*/package"))
        self.assertTrue(package_dirs)

        for package_dir in package_dirs:
            with self.subTest(package=package_dir.parent.name):
                if not is_package_published(package_dir.parent):
                    continue
                manifest = load_valid_manifest(package_dir)
                repository_metadata = read_json(package_dir.parent / "repository.json")
                releases = repository_metadata.get("releases", [])
                versions = {release.get("version") for release in releases}

                self.assertIn(manifest["version"], versions)
                self.assertIn(repository_metadata.get("latest_version", manifest["version"]), versions)

    def test_publish_release_workflow_dropdown_matches_publishable_packages(self):
        workflow_path = REPO_ROOT / ".github" / "workflows" / "publish-release.yml"
        workflow_lines = workflow_path.read_text(encoding="utf-8").splitlines()

        try:
            package_id_index = workflow_lines.index("      package_id:")
        except ValueError:
            self.fail("publish-release.yml must define workflow_dispatch.inputs.package_id")

        try:
            options_index = workflow_lines.index("        options:", package_id_index + 1)
        except ValueError:
            self.fail("publish-release.yml package_id input must expose a static dropdown")

        dropdown_package_ids = []
        for line in workflow_lines[options_index + 1 :]:
            if line.startswith("          - "):
                dropdown_package_ids.append(line.removeprefix("          - ").strip())
                continue
            if dropdown_package_ids:
                break

        self.assertTrue(
            dropdown_package_ids,
            "publish-release.yml package_id dropdown must define at least one package option",
        )
        publishable_package_ids = [
            item["package_id"]
            for item in list_available_release_metadata(REPO_ROOT / "packages")
        ]

        self.assertEqual(
            dropdown_package_ids,
            publishable_package_ids,
            "New publishable package PRs must update .github/workflows/publish-release.yml package_id options.",
        )

    def test_publish_release_workflow_publishes_live_index_after_assets(self):
        workflow_path = REPO_ROOT / ".github" / "workflows" / "publish-release.yml"
        workflow = workflow_path.read_text(encoding="utf-8")

        self.assertIn("concurrency:", workflow)
        self.assertIn("group: publish-extension-release-live-index", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("LIVE_INDEX_BRANCH: live", workflow)
        self.assertIn("LIVE_INDEX_PATH: index.json", workflow)
        self.assertIn("--expected-github-repository", workflow)
        self.assertIn("releases?per_page=100", workflow)
        self.assertIn("Install Python signing dependencies", workflow)
        self.assertIn("Sign release asset sidecars", workflow)
        self.assertIn("tools/sign_repository_assets.py", workflow)
        self.assertIn("AFTERNIGHT_EXTENSION_SIGNING_KEY_ED25519_SEED_B64", workflow)
        self.assertIn("tools/signing/official_keys.json", workflow)
        self.assertIn("Verify selected GitHub Release assets match local files", workflow)
        self.assertIn("Refresh signed metadata sidecars on existing GitHub Release", workflow)
        self.assertIn("Update existing GitHub Release metadata and visibility", workflow)
        self.assertIn("target_draft", workflow)
        self.assertIn("gh api --method PATCH", workflow)
        self.assertIn("Generate repository index candidate", workflow)
        self.assertIn("Build live index update", workflow)
        self.assertIn("tools/update_live_index.py", workflow)
        self.assertIn("Verify selected live index entry is signed", workflow)
        self.assertIn("Verify live index download URLs", workflow)
        self.assertIn("Publish live repository index", workflow)
        self.assertIn("git -C \"$worktree\" rm -r -f --ignore-unmatch .", workflow)
        self.assertIn("if: ${{ inputs.draft == false }}", workflow)

        sign_index = workflow.index("Sign release asset sidecars")
        select_index = workflow.index("Select release archive and metadata sidecar")
        upload_index = workflow.index("Create GitHub Release and upload assets")
        replace_index = workflow.index("Replace GitHub Release assets in place")
        refresh_signature_index = workflow.index("Refresh signed metadata sidecars on existing GitHub Release")
        asset_verify_index = workflow.index("Verify selected GitHub Release assets match local files")
        release_update_index = workflow.index("Update existing GitHub Release metadata and visibility")
        live_candidate_index = workflow.index("Generate repository index candidate")
        live_update_index = workflow.index("Build live index update")
        live_signed_index = workflow.index("Verify selected live index entry is signed")
        live_verify_index = workflow.index("Verify live index download URLs")
        live_publish_index = workflow.index("Publish live repository index")

        self.assertLess(sign_index, select_index)
        self.assertLess(select_index, upload_index)
        self.assertLess(upload_index, asset_verify_index)
        self.assertLess(replace_index, asset_verify_index)
        self.assertLess(refresh_signature_index, asset_verify_index)
        self.assertLess(asset_verify_index, release_update_index)
        self.assertLess(release_update_index, live_candidate_index)
        self.assertLess(live_candidate_index, live_update_index)
        self.assertLess(live_update_index, live_signed_index)
        self.assertLess(live_signed_index, live_verify_index)
        self.assertLess(live_verify_index, live_publish_index)

    def test_cosmic_clarity_processes_have_specific_categories(self):
        package_dir = REPO_ROOT / "packages" / "cosmic_clarity" / "package"
        manifest = load_valid_manifest(package_dir)
        processes = {process["id_suffix"]: process for process in manifest["processes"]}

        self.assertEqual(processes["denoise"]["category"], "denoising")
        self.assertEqual(processes["dark_star"]["category"], "star_object")
        self.assertEqual(processes["super_resolution"]["category"], "sharpening_enhancement")
        self.assertEqual(processes["sharpening"]["category"], "sharpening_enhancement")

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
        self.assertEqual(
            processes["starcomposer"]["capabilities"],
            {"execute": True, "preview": True, "keep_open": True},
        )
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

    def test_veralux_publication_readiness_records_release_state(self):
        package_root = REPO_ROOT / "packages" / "veralux"
        repository_metadata = read_json(package_root / "repository.json")
        readiness = (package_root / "packaging" / "PUBLICATION_READINESS.md").read_text(
            encoding="utf-8"
        )
        packaging_notes = (package_root / "packaging" / "README.md").read_text(encoding="utf-8")

        self.assertIsNot(repository_metadata.get("publish"), False)
        release = repository_metadata["releases"][0]
        self.assertEqual(release["version"], "0.1.0")
        self.assertIn("veralux-v0.1.0", release["asset_base_url"])
        self.assertIn("Status: published as `veralux` version `0.1.0`.", readiness)
        self.assertIn("Representative real-image visual QA", readiness)
        self.assertIn("Manual release testing covered representative", readiness)
        self.assertIn("Release signoff", readiness)
        self.assertIn("Representative QA Signoff", readiness)
        self.assertIn("PUBLICATION_READINESS.md", packaging_notes)
        self.assertIn("published through the official AfterNight extension index", packaging_notes)

    def test_release_metadata_resolves_github_release_tag(self):
        metadata = resolve_release_metadata(REPO_ROOT / "packages", "veralux", "0.1.0")

        self.assertEqual(metadata["package_id"], "veralux")
        self.assertEqual(metadata["version"], "0.1.0")
        self.assertEqual(metadata["release_tag"], "veralux-v0.1.0")
        self.assertEqual(metadata["release_title"], "VeraLux Suite 0.1.0")
        self.assertIn("github.com/emruiz81/afternight-extensions", metadata["asset_base_url"])

    def test_release_metadata_rejects_version_mismatch(self):
        with self.assertRaisesRegex(PackageToolError, "manifest version"):
            resolve_release_metadata(REPO_ROOT / "packages", "veralux", "9.9.9")

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
