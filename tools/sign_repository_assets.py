#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Ezequiel Ruiz

import argparse
import json
import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from afternight_repo.package_tools import PackageToolError, read_json, sha256_file, write_json  # noqa: E402
from afternight_repo.signing import (  # noqa: E402
    SIGNING_SECRET_ENV,
    SigningError,
    derive_public_key_base64,
    load_public_keys,
    signed_metadata,
    verify_payload_signature,
    signing_payload_for_metadata,
)


def matching_metadata_paths(assets_dir, package_id, version):
    paths = []
    for metadata_path in sorted(Path(assets_dir).glob("*.metadata.json")):
        metadata = read_json(metadata_path)
        if metadata.get("package_id") == package_id and metadata.get("version") == version:
            paths.append(metadata_path)
    return paths


def verify_archive_hash(assets_dir, metadata_path, metadata):
    archive_path = Path(assets_dir) / metadata.get("name", "")
    if not archive_path.is_file():
        raise PackageToolError(f"{metadata_path}: referenced archive is missing")
    actual_hash = "sha256:" + sha256_file(archive_path)
    if metadata.get("package_hash") != actual_hash:
        raise PackageToolError(f"{metadata_path}: package_hash does not match compressed archive")
    return archive_path


def main():
    parser = argparse.ArgumentParser(description="Sign AfterNight extension release assets.")
    parser.add_argument("--assets-dir", default="dist", help="Directory containing .tar.zst assets and sidecars")
    parser.add_argument("--package-id", required=True, help="Package id to sign")
    parser.add_argument("--version", required=True, help="Package version to sign")
    parser.add_argument("--key-id", required=True, help="Committed signing key id")
    parser.add_argument(
        "--public-keys",
        default="tools/signing/official_keys.json",
        help="JSON registry containing committed public signing keys",
    )
    parser.add_argument(
        "--secret-env",
        default=SIGNING_SECRET_ENV,
        help="Environment variable containing the base64 Ed25519 seed",
    )
    parser.add_argument("--signature-detail", help="Human-readable signature detail for index entries")
    args = parser.parse_args()

    try:
        public_keys = load_public_keys(args.public_keys)
        public_key = public_keys.get(args.key_id)
        if public_key is None:
            raise SigningError(f"{args.public_keys}: missing key_id {args.key_id}")

        seed = os.environ.get(args.secret_env, "").strip()
        if not seed:
            raise SigningError(f"{args.secret_env} is required to sign release assets")
        derived_public_key = derive_public_key_base64(seed)
        if derived_public_key != public_key:
            raise SigningError("signing seed does not match the committed public key for this key id")

        metadata_paths = matching_metadata_paths(args.assets_dir, args.package_id, args.version)
        if not metadata_paths:
            raise PackageToolError(f"no built assets found for {args.package_id} {args.version}")

        signed = []
        for metadata_path in metadata_paths:
            metadata = read_json(metadata_path)
            archive_path = verify_archive_hash(args.assets_dir, metadata_path, metadata)
            metadata = signed_metadata(
                metadata,
                signature_key_id=args.key_id,
                seed_base64=seed,
                public_key_base64=public_key,
                signature_detail=args.signature_detail,
            )
            payload = signing_payload_for_metadata(metadata, args.key_id)
            if not verify_payload_signature(payload, public_key, metadata["signature"]):
                raise SigningError(f"{metadata_path}: generated signature failed verification")
            write_json(metadata_path, metadata)

            signature_path = Path(str(archive_path) + ".sig")
            signature_path.write_text(metadata["signature"] + "\n", encoding="ascii", newline="\n")
            signed.append(
                {
                    "metadata": str(metadata_path),
                    "archive": str(archive_path),
                    "signature": str(signature_path),
                    "key_id": args.key_id,
                }
            )
    except (OSError, json.JSONDecodeError, PackageToolError, SigningError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(signed, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
