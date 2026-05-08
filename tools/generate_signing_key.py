#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Ezequiel Ruiz

import argparse
import json
import secrets
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from afternight_repo.signing import SIGNING_SECRET_ENV, derive_public_key_base64, encode_base64  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Generate an AfterNight extension Ed25519 signing key.")
    parser.add_argument("--key-id", required=True, help="Public key id to commit with the app/repository")
    parser.add_argument("--output-public-key", help="Optional path for a public-key JSON fragment")
    args = parser.parse_args()

    seed_base64 = encode_base64(secrets.token_bytes(32))
    public_key_base64 = derive_public_key_base64(seed_base64)
    public_key_entry = {
        "key_id": args.key_id,
        "algorithm": "ed25519",
        "public_key_base64": public_key_base64,
        "status": "active",
    }

    print(f"GitHub secret {SIGNING_SECRET_ENV}:")
    print(seed_base64)
    print()
    print("Public key entry to commit:")
    print(json.dumps(public_key_entry, indent=2))

    if args.output_public_key:
        Path(args.output_public_key).write_text(
            json.dumps({"keys": [public_key_entry]}, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
