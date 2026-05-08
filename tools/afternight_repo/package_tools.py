# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Ezequiel Ruiz

import ast
import fnmatch
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from afternight_repo.signing import (
    ED25519_SIGNATURE_BYTES,
    SIGNATURE_ALGORITHM,
    SIGNATURE_STATE_VERIFIED,
    SigningError,
    decode_base64_exact,
)


SUPPORTED_RUNTIME_TARGETS = (
    "linux-clang-x86_64",
    "windows-msvc-x86_64",
)

PROVENANCE_FIELDS = (
    "attribution",
    "original_author",
    "original_project",
    "original_source_url",
    "upstream_commit",
)

SCHEMA_VERSION = 1
PACKAGE_FORMAT_VERSION = 1
PROTOCOL_VERSION = 1
SDK_VERSION = 1
DEFAULT_SIGNATURE_STATE = "unsigned"
SIGNATURE_STATES = ("unknown", "unsigned", "verified", "failed")

SDK_BACKENDS = ("runtime", "protocol", "rpc")
RPC_BACKEND_AVAILABLE = False
DEPENDENCY_CONTEXTS = ("private", "shared_host", "shared_group")
SHARED_HOST_PROFILES = ("scientific_core",)

GPL_RUNTIME_LICENSES = {
    "GPL-3.0",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
}

ENGINE_BACKED_IMPORTS = {
    "_afternight_runtime",
    "afternight.calibration",
    "afternight.core",
    "afternight.io",
    "afternight.registration",
    "afternight.runtime",
    "afternight.stacking",
}

NATIVE_UI_IMPORTS = {
    "afternight.ProcessExtension",
    "afternight.RTPreviewExtension",
    "afternight.WorkflowExtension",
    "afternight.ui",
}

NATIVE_CONTROL_CAPABILITY_KEYS = {
    "afternight_controls",
    "native_controls",
    "native_process_controls",
    "native_process_window",
}

EXCLUDED_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "extension_package_receipt.json",
}

EXCLUDED_PATTERNS = (
    "*.pyc",
    "*.pyo",
    "*.metadata.json",
)


class PackageToolError(RuntimeError):
    """Raised when repository package tooling rejects package metadata."""


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def build_package(package_dir, output_dir, compression_level=10, runtime_targets=None, asset_name=None):
    package_dir = Path(package_dir)
    output_dir = Path(output_dir)
    manifest = load_valid_manifest(package_dir)

    targets = _normalize_runtime_targets(
        runtime_targets if runtime_targets is not None else manifest.get("runtime_targets"),
        allow_empty=False,
    )
    extension_id = manifest["id"]
    version = manifest["version"]
    if asset_name is None:
        asset_name = f"{extension_id}-{version}-{_asset_target_slug(targets)}.tar.zst"
    _validate_asset_name(asset_name)

    level = _normalize_compression_level(compression_level)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / asset_name

    with tempfile.TemporaryDirectory() as temp:
        tar_path = Path(temp) / f"{asset_name[:-4]}.tar"
        _write_deterministic_tar(package_dir, tar_path, extension_id)
        _compress_with_zstd(tar_path, archive_path, level)

    package_hash = "sha256:" + sha256_file(archive_path)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "package_id": extension_id,
        "version": version,
        "name": asset_name,
        "path": archive_path.name,
        "package_hash": package_hash,
        "sha256": package_hash.removeprefix("sha256:"),
        "size_bytes": archive_path.stat().st_size,
        "runtime_targets": targets,
        "compression": "zstd",
        "compression_level": level,
    }
    write_json(_metadata_path(archive_path), metadata)
    return metadata


def generate_index(
    packages_root,
    assets_dir,
    repository="afternight-extensions",
    updated_at=None,
    base_url="",
    official=True,
):
    packages_root = Path(packages_root)
    assets_dir = Path(assets_dir)
    if updated_at is None:
        raise PackageToolError("updated_at is required for deterministic index generation")

    packages = []
    for package_source in sorted(packages_root.glob("*/package")):
        if (package_source / "extension.json").is_file():
            if not is_package_published(package_source.parent):
                continue
            packages.append(_generate_package_index_entry(package_source, assets_dir, base_url))

    return {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "official": bool(official),
        "updated_at": updated_at,
        "extensions": packages,
    }


def load_valid_manifest(package_dir):
    package_dir = Path(package_dir)
    manifest_path = package_dir / "extension.json"
    if not manifest_path.is_file():
        raise PackageToolError(f"missing manifest: {manifest_path}")

    manifest = read_json(manifest_path)
    required_strings = (
        "id",
        "name",
        "version",
        "summary",
        "description",
        "author",
        "license",
        "publisher_id",
        "type",
        "entry_point",
        "category",
        "launch_mode",
        "sdk_backend",
    )
    for key in required_strings:
        _require_string(manifest, key, manifest_path)

    for key, expected in (
        ("package_format_version", PACKAGE_FORMAT_VERSION),
        ("protocol_version", PROTOCOL_VERSION),
        ("sdk_version", SDK_VERSION),
    ):
        value = manifest.get(key)
        if not isinstance(value, int) or value != expected:
            raise PackageToolError(f"{manifest_path}: {key} must be integer {expected}")

    if manifest["type"] != "python":
        raise PackageToolError(f"{manifest_path}: only python extension packages are supported")
    if manifest["launch_mode"] not in ("single_image", "workflow"):
        raise PackageToolError(f"{manifest_path}: launch_mode must be single_image or workflow")
    if manifest["sdk_backend"] not in SDK_BACKENDS:
        raise PackageToolError(f"{manifest_path}: sdk_backend must be runtime, protocol, or rpc")

    _validate_identifier(manifest["id"], manifest_path)
    _validate_runtime_targets(manifest.get("runtime_targets"), manifest_path, allow_empty=True)
    _validate_tags(manifest.get("tags"), manifest_path)
    _validate_entry_point(package_dir, manifest["entry_point"])
    _validate_license(package_dir)
    _validate_dependencies(package_dir, manifest, manifest_path)
    _validate_host_mode_policy(package_dir, manifest, manifest_path)
    return manifest


def is_package_published(package_root):
    repository_metadata_path = Path(package_root) / "repository.json"
    if not repository_metadata_path.is_file():
        return True
    repository_metadata = read_json(repository_metadata_path)
    return repository_metadata.get("publish", True) is not False


def _generate_package_index_entry(package_source, assets_dir, base_url):
    manifest = load_valid_manifest(package_source)
    package_root = package_source.parent
    repository_metadata_path = package_root / "repository.json"
    if not repository_metadata_path.is_file():
        raise PackageToolError(f"missing repository release metadata: {repository_metadata_path}")

    repository_metadata = read_json(repository_metadata_path)
    releases_metadata = repository_metadata.get("releases")
    if not isinstance(releases_metadata, list) or not releases_metadata:
        raise PackageToolError(f"{repository_metadata_path}: releases must be a non-empty array")
    release_versions = [
        release.get("version")
        for release in releases_metadata
        if isinstance(release, dict) and isinstance(release.get("version"), str)
    ]
    historical_versions = sorted(set(release_versions) - {manifest["version"]})
    if historical_versions:
        raise PackageToolError(
            f"{repository_metadata_path}: generated index supports the current package "
            f"version only ({manifest['version']}); remove historical release metadata "
            f"for {', '.join(historical_versions)}"
        )

    all_assets = _load_asset_metadata(assets_dir)
    assets_by_version = {}
    for asset in all_assets:
        if asset.get("package_id") == manifest["id"]:
            assets_by_version.setdefault(asset.get("version"), []).append(asset)

    if not assets_by_version:
        raise PackageToolError(f"no built assets found for {manifest['id']} in {assets_dir}")

    releases = []
    for release_metadata in releases_metadata:
        release = _generate_release_entry(
            manifest,
            release_metadata,
            assets_by_version,
            repository_metadata_path,
            base_url,
        )
        releases.append(release)

    latest_version = repository_metadata.get("latest_version", manifest["version"])
    if not isinstance(latest_version, str) or not latest_version:
        raise PackageToolError(f"{repository_metadata_path}: latest_version must be a non-empty string")
    if latest_version not in {release["version"] for release in releases}:
        raise PackageToolError(f"{repository_metadata_path}: latest_version {latest_version} has no matching release")

    package = {
        "id": manifest["id"],
        "name": manifest["name"],
        "summary": manifest["summary"],
        "description": manifest["description"],
        "author": manifest["author"],
        "license": manifest["license"],
        "publisher_id": manifest["publisher_id"],
        "latest_version": latest_version,
        "tags": manifest.get("tags", []),
        "releases": releases,
    }
    for key in (*PROVENANCE_FIELDS, "homepage_url", "repository_url", "support_url", "icon_url"):
        if manifest.get(key):
            package[key] = manifest[key]
    return package


def _generate_release_entry(manifest, release_metadata, assets_by_version, metadata_path, base_url):
    version = release_metadata.get("version")
    if not isinstance(version, str) or not version:
        raise PackageToolError(f"{metadata_path}: release.version must be a non-empty string")
    min_app_version = release_metadata.get("min_app_version")
    if not isinstance(min_app_version, str) or not min_app_version:
        raise PackageToolError(f"{metadata_path}: release {version} must declare min_app_version")

    matching_assets = sorted(assets_by_version.get(version, []), key=lambda asset: asset["name"])
    if not matching_assets:
        raise PackageToolError(f"{metadata_path}: release {version} has no built assets")

    release_targets = sorted({target for asset in matching_assets for target in asset.get("runtime_targets", [])})
    if not release_targets:
        release_targets = _normalize_runtime_targets(manifest.get("runtime_targets"), allow_empty=False)

    release_base_url = release_metadata.get("asset_base_url", base_url)
    if not isinstance(release_base_url, str):
        raise PackageToolError(f"{metadata_path}: release {version} asset_base_url must be a string")
    release_signature_state = release_metadata.get("signature_state", DEFAULT_SIGNATURE_STATE)
    if release_signature_state not in SIGNATURE_STATES:
        raise PackageToolError(
            f"{metadata_path}: release {version} signature_state must be one of {', '.join(SIGNATURE_STATES)}"
        )
    if release_signature_state == SIGNATURE_STATE_VERIFIED:
        raise PackageToolError(
            f"{metadata_path}: release {version} must not declare signature_state verified; "
            "verified signatures are emitted only from signed asset sidecars"
        )
    for signature_key in ("signature_algorithm", "signature_key_id", "signature"):
        if release_metadata.get(signature_key):
            raise PackageToolError(
                f"{metadata_path}: release {version} must not declare {signature_key}; "
                "asset signing metadata is generated by tools/sign_repository_assets.py"
            )

    assets = []
    for asset in matching_assets:
        targets = _normalize_runtime_targets(asset.get("runtime_targets"), allow_empty=False)
        signature_state = asset.get("signature_state", release_signature_state)
        _validate_index_asset_signature(asset, metadata_path, version)
        asset_entry = {
            "name": asset["name"],
            "download_url": _download_url(release_base_url, asset["name"]),
            "package_hash": asset["package_hash"],
            "signature_state": signature_state,
            "runtime_targets": targets,
        }
        signature_detail = asset.get("signature_detail", release_metadata.get("signature_detail"))
        if signature_detail:
            asset_entry["signature_detail"] = signature_detail
        for signature_key in ("signature_algorithm", "signature_key_id", "signature"):
            if asset.get(signature_key):
                asset_entry[signature_key] = asset[signature_key]
        assets.append(asset_entry)

    release = {
        "version": version,
        "min_app_version": min_app_version,
        "package_format_version": PACKAGE_FORMAT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "sdk_version": SDK_VERSION,
        "sdk_backend": manifest["sdk_backend"],
        "launch_mode": manifest["launch_mode"],
        "runtime_targets": release_targets,
        "assets": assets,
    }
    for key in ("changelog", "published_at"):
        if release_metadata.get(key):
            release[key] = release_metadata[key]
    return release


def _write_deterministic_tar(package_dir, tar_path, archive_root):
    paths = _collect_package_paths(package_dir)
    with tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as archive:
        root_info = tarfile.TarInfo(archive_root)
        root_info.type = tarfile.DIRTYPE
        root_info.mode = 0o755
        _apply_stable_tar_metadata(root_info)
        archive.addfile(root_info)

        for path in paths:
            relative = path.relative_to(package_dir).as_posix()
            archive_name = f"{archive_root}/{relative}"
            _validate_archive_path(archive_name)
            stat = path.stat()
            info = tarfile.TarInfo(archive_name)
            _apply_stable_tar_metadata(info)
            if path.is_dir():
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                archive.addfile(info)
            elif path.is_file():
                info.type = tarfile.REGTYPE
                info.mode = 0o755 if stat.st_mode & 0o111 else 0o644
                info.size = stat.st_size
                with path.open("rb") as handle:
                    archive.addfile(info, handle)
            else:
                raise PackageToolError(f"unsupported package entry type: {path}")


def _collect_package_paths(package_dir):
    paths = []
    for path in Path(package_dir).rglob("*"):
        if _should_skip(path):
            continue
        if path.is_symlink():
            raise PackageToolError(f"symlinks are not allowed in packages: {path}")
        if not path.is_dir() and not path.is_file():
            raise PackageToolError(f"unsupported package entry type: {path}")
        paths.append(path)
    return sorted(paths, key=lambda path: path.relative_to(package_dir).as_posix())


def _apply_stable_tar_metadata(info):
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""


def _ensure_zstd():
    if shutil.which("zstd") is not None:
        return
    if sys.platform == "win32" and shutil.which("winget") is not None:
        print("zstd not found — installing via winget (Meta.Zstandard)...", flush=True)
        subprocess.run(
            [
                "winget",
                "install",
                "--id",
                "Meta.Zstandard",
                "--silent",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            check=False,
        )
        # winget exits 0 on success, but also uses non-zero for "no upgrade available" or
        # "already installed" — treat those as success too (REBOOT_REQUIRED = 0x3010, etc.)
        # We rely on the subsequent shutil.which check rather than the exit code.

        # winget modifies the user or machine PATH; refresh the current process PATH so shutil.which can find it
        import os

        for scope in ("Machine", "User"):
            reg_path = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"[System.Environment]::GetEnvironmentVariable('PATH', '{scope}')",
                ],
                check=False,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.strip()
            if reg_path:
                os.environ["PATH"] = reg_path + os.pathsep + os.environ.get("PATH", "")
        # winget also installs a CLI alias into %LOCALAPPDATA%\Microsoft\WinGet\Links
        winget_links = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links")
        if os.path.isdir(winget_links):
            os.environ["PATH"] = winget_links + os.pathsep + os.environ.get("PATH", "")
        if shutil.which("zstd") is None:
            raise PackageToolError("zstd was installed but is not yet on PATH; open a new terminal and retry")
    elif sys.platform == "win32":
        raise PackageToolError(
            "zstd is required but was not found. "
            "Install it with: winget install Meta.Zstandard  "
            "(or via Chocolatey: choco install zstandard, or Scoop: scoop install zstd)"
        )
    else:
        raise PackageToolError(
            "zstd is required but was not found. Install it with your package manager (e.g. apt-get install zstd)"
        )


def _compress_with_zstd(tar_path, archive_path, compression_level):
    _ensure_zstd()
    result = subprocess.run(
        [
            "zstd",
            "-q",
            "-f",
            "--no-progress",
            "-T1",
            f"-{compression_level}",
            "-o",
            str(archive_path),
            str(tar_path),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise PackageToolError(f"zstd compression failed: {result.stderr.strip()}")


def _load_asset_metadata(assets_dir):
    assets_dir = Path(assets_dir)
    if not assets_dir.is_dir():
        raise PackageToolError(f"assets directory does not exist: {assets_dir}")

    assets = []
    for metadata_path in sorted(assets_dir.glob("*.metadata.json")):
        asset = read_json(metadata_path)
        archive_path = assets_dir / asset.get("name", "")
        if not archive_path.is_file():
            raise PackageToolError(f"{metadata_path}: referenced archive is missing")
        actual_hash = "sha256:" + sha256_file(archive_path)
        if asset.get("package_hash") != actual_hash:
            raise PackageToolError(f"{metadata_path}: package_hash does not match compressed archive")
        _normalize_runtime_targets(asset.get("runtime_targets"), allow_empty=False)
        if asset.get("compression") != "zstd":
            raise PackageToolError(f"{metadata_path}: compression must be zstd")
        _validate_asset_metadata_signature(asset, metadata_path)
        assets.append(asset)
    return assets


def _validate_asset_metadata_signature(asset, metadata_path):
    signature_state = asset.get("signature_state", DEFAULT_SIGNATURE_STATE)
    if signature_state not in SIGNATURE_STATES:
        raise PackageToolError(f"{metadata_path}: signature_state must be one of {', '.join(SIGNATURE_STATES)}")

    signature_fields = ("signature_algorithm", "signature_key_id", "signature")
    if signature_state == SIGNATURE_STATE_VERIFIED:
        for key in signature_fields:
            if not isinstance(asset.get(key), str) or not asset[key]:
                raise PackageToolError(f"{metadata_path}: verified assets must declare {key}")
        if asset["signature_algorithm"] != SIGNATURE_ALGORITHM:
            raise PackageToolError(f"{metadata_path}: signature_algorithm must be {SIGNATURE_ALGORITHM}")
        try:
            decode_base64_exact(asset["signature"], ED25519_SIGNATURE_BYTES, "signature")
        except SigningError as exc:
            raise PackageToolError(f"{metadata_path}: {exc}") from exc
        if not isinstance(asset.get("signature_detail"), str) or not asset["signature_detail"]:
            raise PackageToolError(f"{metadata_path}: verified assets must declare signature_detail")
        return

    for key in signature_fields:
        if asset.get(key):
            raise PackageToolError(
                f"{metadata_path}: {signature_state} assets must not declare generated signature field {key}"
            )


def _validate_index_asset_signature(asset, metadata_path, version):
    try:
        _validate_asset_metadata_signature(asset, metadata_path)
    except PackageToolError as exc:
        raise PackageToolError(
            f"{metadata_path}: release {version} asset {asset.get('name', '<unknown>')}: {exc}"
        ) from exc


def _require_string(data, key, source):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PackageToolError(f"{source}: {key} must be a non-empty string")


def _validate_identifier(value, source):
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
    if any(character not in allowed for character in value) or value[0] in "-_":
        raise PackageToolError(f"{source}: id must use lowercase letters, numbers, dashes, or underscores")


def _validate_runtime_targets(value, source=None, allow_empty=False):
    if value is None:
        return [] if allow_empty else list(SUPPORTED_RUNTIME_TARGETS)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        location = f"{source}: " if source else ""
        raise PackageToolError(f"{location}runtime_targets must be an array of strings")
    return _normalize_runtime_targets(value, allow_empty=allow_empty)


def _normalize_runtime_targets(value, allow_empty):
    if value is None:
        value = []
    targets = sorted(dict.fromkeys(value))
    if not targets and not allow_empty:
        targets = list(SUPPORTED_RUNTIME_TARGETS)
    unknown = sorted(set(targets) - set(SUPPORTED_RUNTIME_TARGETS))
    if unknown:
        raise PackageToolError(f"unsupported runtime target(s): {', '.join(unknown)}")
    return targets


def _validate_tags(value, source):
    if value is None:
        return
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PackageToolError(f"{source}: tags must be an array of strings")


def _validate_entry_point(package_dir, entry_point):
    if ":" in entry_point:
        module_name = entry_point.split(":", 1)[0]
    else:
        module_name = entry_point
    module_path = Path(*module_name.split("."))
    module_file = package_dir / module_path.with_suffix(".py")
    package_init = package_dir / module_path / "__init__.py"
    if not module_file.is_file() and not package_init.is_file():
        raise PackageToolError(f"{package_dir / 'extension.json'}: entry_point does not resolve to a package file")


def _validate_license(package_dir):
    if not any((package_dir / name).is_file() for name in ("LICENSE", "LICENSE.md", "LICENSE.txt")):
        raise PackageToolError(f"{package_dir}: package-local LICENSE file is required")


def _validate_dependencies(package_dir, manifest, manifest_path):
    dependencies = manifest.get("dependencies")
    if dependencies is None:
        return
    if not isinstance(dependencies, dict):
        raise PackageToolError(f"{manifest_path}: dependencies must be an object")

    context = dependencies.get("dependency_context")
    if not isinstance(context, str) or not context:
        raise PackageToolError(f"{manifest_path}: dependencies.dependency_context must be a non-empty string")
    if context not in DEPENDENCY_CONTEXTS:
        allowed = ", ".join(DEPENDENCY_CONTEXTS)
        raise PackageToolError(f"{manifest_path}: dependencies.dependency_context must be one of {allowed}")

    if context == "shared_host":
        profile = dependencies.get("shared_host_profile")
        if profile not in SHARED_HOST_PROFILES:
            allowed = ", ".join(SHARED_HOST_PROFILES)
            raise PackageToolError(f"{manifest_path}: dependencies.shared_host_profile must be one of {allowed}")
        if dependencies.get("requirements_file"):
            raise PackageToolError(
                f"{manifest_path}: shared_host dependencies must use a host-curated profile, "
                "not a package requirements_file"
            )
    elif context == "shared_group":
        shared_group = dependencies.get("shared_group")
        if not isinstance(shared_group, str) or not shared_group:
            raise PackageToolError(f"{manifest_path}: shared_group dependencies must declare dependencies.shared_group")

    pip = dependencies.get("pip")
    if pip is not None and not isinstance(pip, dict):
        raise PackageToolError(f"{manifest_path}: dependencies.pip must be an object")

    requirements_file = dependencies.get("requirements_file")
    if requirements_file is not None:
        requirements_path = _resolve_package_relative_path(
            package_dir,
            requirements_file,
            manifest_path,
            "dependencies.requirements_file",
        )
        if not requirements_path.is_file():
            raise PackageToolError(
                f"{manifest_path}: dependencies.requirements_file does not exist: {requirements_file}"
            )
        if not isinstance(pip, dict):
            raise PackageToolError(f"{manifest_path}: dependencies.pip is required when requirements_file is present")
        if pip.get("require_hashes") is not True:
            raise PackageToolError(
                f"{manifest_path}: dependencies.pip.require_hashes must be true when requirements_file is present"
            )
        _validate_requirements_lock(requirements_path)

    if isinstance(pip, dict):
        _validate_pip_path_list(package_dir, manifest_path, pip, "find_links", must_exist=True)
        for key in ("index_urls", "extra_index_urls"):
            _validate_string_list(manifest_path, pip, f"dependencies.pip.{key}", key)

    if dependencies:
        _validate_third_party_notices(package_dir)


def _validate_third_party_notices(package_dir):
    notices_path = package_dir / "THIRD_PARTY_NOTICES.md"
    if not notices_path.is_file():
        raise PackageToolError(f"{package_dir}: THIRD_PARTY_NOTICES.md is required when dependencies are declared")


def _validate_pip_path_list(package_dir, manifest_path, pip, key, must_exist):
    values = pip.get(key)
    if values is None:
        return
    if not isinstance(values, list) or not all(isinstance(item, str) and item for item in values):
        raise PackageToolError(f"{manifest_path}: dependencies.pip.{key} must be an array of strings")
    for value in values:
        path = _resolve_package_relative_path(
            package_dir,
            value,
            manifest_path,
            f"dependencies.pip.{key}",
        )
        if must_exist and not path.exists():
            raise PackageToolError(f"{manifest_path}: dependencies.pip.{key} path does not exist: {value}")


def _validate_string_list(manifest_path, data, display_key, key):
    values = data.get(key)
    if values is None:
        return
    if not isinstance(values, list) or not all(isinstance(item, str) and item for item in values):
        raise PackageToolError(f"{manifest_path}: {display_key} must be an array of strings")


def _resolve_package_relative_path(package_dir, value, source, key):
    if not isinstance(value, str) or not value:
        raise PackageToolError(f"{source}: {key} must be a non-empty string")
    try:
        _validate_archive_path(value)
    except PackageToolError as exc:
        raise PackageToolError(f"{source}: {key} must be a safe package-local path") from exc

    path = package_dir / Path(value)
    package_root = package_dir.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(package_root)
    except ValueError as exc:
        raise PackageToolError(f"{source}: {key} must stay inside the package root") from exc
    return path


def _validate_requirements_lock(path):
    requirement_count = 0
    for line in _iter_logical_requirement_lines(path):
        if not line or line.startswith("-"):
            continue
        requirement_count += 1
        requirement_part = line.split("--hash=", 1)[0]
        if "==" not in requirement_part:
            raise PackageToolError(f"{path}: hashed requirements must pin exact versions with ==")
        hashes = [part for part in line.split() if part.startswith("--hash=")]
        if not hashes:
            raise PackageToolError(f"{path}: every requirement must include at least one --hash=sha256: value")
        if any(not item.startswith("--hash=sha256:") for item in hashes):
            raise PackageToolError(f"{path}: requirement hashes must use sha256")

    if requirement_count == 0:
        raise PackageToolError(f"{path}: requirements lock must contain at least one requirement")


def _iter_logical_requirement_lines(path):
    pending = ""
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            pending += line[:-1].strip() + " "
            continue
        yield (pending + line).strip()
        pending = ""
    if pending.strip():
        yield pending.strip()


def _validate_host_mode_policy(package_dir, manifest, manifest_path):
    sdk_backend = manifest["sdk_backend"]
    license_id = manifest["license"].strip()

    if sdk_backend == "runtime" and license_id not in GPL_RUNTIME_LICENSES:
        allowed = ", ".join(sorted(GPL_RUNTIME_LICENSES))
        raise PackageToolError(
            f"{manifest_path}: sdk_backend runtime packages must use a GPL-3.0 compatible package license ({allowed})"
        )

    if sdk_backend == "rpc" and not RPC_BACKEND_AVAILABLE:
        raise PackageToolError(
            f"{manifest_path}: sdk_backend rpc is reserved until the target "
            "AfterNight release ships RPC extension hosting"
        )

    if sdk_backend == "protocol":
        native_capability = _find_native_control_capability(manifest)
        if native_capability:
            raise PackageToolError(
                f"{manifest_path}: sdk_backend protocol packages must not declare "
                f"native-control capability {native_capability}"
            )

        engine_import = _find_engine_backed_import(package_dir)
        if engine_import:
            source_path, module_name = engine_import
            raise PackageToolError(
                f"{source_path}: sdk_backend protocol packages must not import Engine-backed module {module_name}"
            )

        native_ui_import = _find_native_ui_import(package_dir)
        if native_ui_import:
            source_path, module_name = native_ui_import
            raise PackageToolError(
                f"{source_path}: sdk_backend protocol packages must not import "
                f"native afternight.ui surface {module_name}; use afternight.ui_protocol"
            )


def _find_engine_backed_import(package_dir):
    for source_path in _iter_python_sources(package_dir):
        try:
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        except SyntaxError as exc:
            raise PackageToolError(f"{source_path}: Python syntax error: {exc.msg}") from exc

        for node in ast.walk(tree):
            module_name = _engine_backed_import_name(node)
            if module_name:
                return source_path, module_name
    return None


def _engine_backed_import_name(node):
    if isinstance(node, ast.Import):
        for alias in node.names:
            matched = _match_engine_backed_module(alias.name)
            if matched:
                return matched
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        matched = _match_engine_backed_module(module)
        if matched:
            return matched
        if module == "afternight":
            for alias in node.names:
                candidate = f"afternight.{alias.name}"
                matched = _match_engine_backed_module(candidate)
                if matched:
                    return matched
        elif module.startswith("afternight."):
            for alias in node.names:
                candidate = f"{module}.{alias.name}"
                matched = _match_engine_backed_module(candidate)
                if matched:
                    return matched
    return None


def _match_engine_backed_module(module_name):
    if module_name in ENGINE_BACKED_IMPORTS:
        return module_name
    for banned in ENGINE_BACKED_IMPORTS:
        if module_name.startswith(banned + "."):
            return banned
    return None


def _find_native_ui_import(package_dir):
    for source_path in _iter_python_sources(package_dir):
        try:
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        except SyntaxError as exc:
            raise PackageToolError(f"{source_path}: Python syntax error: {exc.msg}") from exc

        for node in ast.walk(tree):
            module_name = _native_ui_import_name(node)
            if module_name:
                return source_path, module_name
    return None


def _native_ui_import_name(node):
    if isinstance(node, ast.Import):
        for alias in node.names:
            matched = _match_native_ui_module(alias.name)
            if matched:
                return matched
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        matched = _match_native_ui_module(module)
        if matched:
            return matched
        if module == "afternight":
            for alias in node.names:
                candidate = f"afternight.{alias.name}"
                matched = _match_native_ui_module(candidate)
                if matched:
                    return matched
        elif module.startswith("afternight."):
            for alias in node.names:
                candidate = f"{module}.{alias.name}"
                matched = _match_native_ui_module(candidate)
                if matched:
                    return matched
    return None


def _match_native_ui_module(module_name):
    if module_name in NATIVE_UI_IMPORTS:
        return module_name
    if module_name.startswith("afternight.ui."):
        return "afternight.ui"
    return None


def _iter_python_sources(package_dir):
    for path in Path(package_dir).rglob("*.py"):
        if _should_skip(path):
            continue
        yield path


def _find_native_control_capability(manifest):
    for key, value in _walk_manifest_values(manifest):
        if key in NATIVE_CONTROL_CAPABILITY_KEYS and value is True:
            return key
    return None


def _walk_manifest_values(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk_manifest_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_manifest_values(child)


def _should_skip(path):
    if any(part == "__pycache__" for part in path.parts):
        return True
    if path.name in EXCLUDED_NAMES:
        return True
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDED_PATTERNS)


def _validate_archive_path(path):
    pure = Path(path)
    parts = pure.parts
    if pure.is_absolute() or ".." in parts or not parts:
        raise PackageToolError(f"unsafe archive path: {path}")
    if any(not part for part in parts):
        raise PackageToolError(f"unsafe archive path: {path}")
    if "\\" in path or ":" in path:
        raise PackageToolError(f"unsafe archive path: {path}")


def _validate_asset_name(name):
    if not name.endswith(".tar.zst"):
        raise PackageToolError("asset name must end in .tar.zst")
    _validate_archive_path(name)
    if "/" in name:
        raise PackageToolError("asset name must not include directories")


def _normalize_compression_level(value):
    try:
        level = int(value)
    except (TypeError, ValueError) as exc:
        raise PackageToolError("compression level must be an integer") from exc
    if level < 1 or level > 19:
        raise PackageToolError("compression level must be between 1 and 19")
    return level


def _asset_target_slug(targets):
    if targets == list(SUPPORTED_RUNTIME_TARGETS):
        return "all"
    if len(targets) == 1:
        return targets[0]
    digest = hashlib.sha256(",".join(targets).encode("utf-8")).hexdigest()[:8]
    return f"multi-{digest}"


def _metadata_path(archive_path):
    return Path(str(archive_path) + ".metadata.json")


def _download_url(base_url, asset_name):
    if not base_url:
        return asset_name
    return base_url.rstrip("/") + "/" + asset_name
