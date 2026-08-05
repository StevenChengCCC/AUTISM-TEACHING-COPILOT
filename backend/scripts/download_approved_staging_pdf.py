#!/usr/bin/env python3
"""Download one approved synthetic staging PDF without exposing signed URLs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from run_paid_staging_quality_round import ApiClient, RoundFailure


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="https://api.autismteachingcopilot.com")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--package-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--preset",
        default="complete_kit",
        choices=(
            "complete_kit",
            "teacher_desk",
            "classroom_materials",
            "data_and_closeout",
        ),
    )
    parser.add_argument("--page-size", default="Letter", choices=("Letter", "A4"))
    parser.add_argument("--text-profile", default="standard", choices=("standard", "large"))
    parser.add_argument("--confirm-synthetic", action="store_true")
    args = parser.parse_args()

    if not args.confirm_synthetic:
        raise RoundFailure("Refusing to download without --confirm-synthetic")
    token = args.token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise RoundFailure("Token file is empty")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    client = ApiClient(args.api_base, token, timeout=180)

    readiness = client.request(
        "GET", f"/api/v2/lesson-packages/{args.package_id}/print-readiness"
    )
    if not readiness.get("ready"):
        blocker_ids = [
            str(item.get("blockerId")) for item in readiness.get("blockers", [])
        ]
        raise RoundFailure(
            "Package is not print ready; blockers=" + ",".join(blocker_ids)
        )
    package = client.request(
        "GET", f"/api/v2/lesson-packages/{args.package_id}"
    )
    material_ids = [
        str(item["id"])
        for item in package.get("materials", [])
        if item.get("id")
    ]

    artifact = client.request(
        "POST",
        f"/api/v2/lesson-packages/{args.package_id}/pdf-artifacts",
        {
            "materialIds": material_ids,
            "printPreset": args.preset,
            "pageSize": args.page_size,
            "locale": "en-US",
            "tableOfContents": True,
            "pageNumbers": True,
            "textProfile": args.text_profile,
            "reviewedConfirmation": True,
        },
    )
    body = client.request("GET", artifact["downloadUrl"], expect_json=False)
    if not body.startswith(b"%PDF-"):
        raise RoundFailure("Downloaded artifact is not a PDF")

    pdf_name = Path(
        str(artifact.get("filename") or artifact.get("fileName") or "lesson-kit.pdf")
    ).name
    (args.output_dir / pdf_name).write_bytes(body)
    safe = {
        key: value
        for key, value in artifact.items()
        if key not in {"downloadUrl", "expiresAt"}
    }
    safe["sha256"] = hashlib.sha256(body).hexdigest()
    safe["downloadVerified"] = True
    (args.output_dir / "pdf-artifact.json").write_text(
        json.dumps(safe, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"PASS: {pdf_name}; pages={artifact['pageCount']}; bytes={len(body)}; "
        f"sha256={safe['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
