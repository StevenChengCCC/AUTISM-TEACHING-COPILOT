#!/usr/bin/env python3
"""Regenerate bounded synthetic staging visuals and save reviewable evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_paid_staging_quality_round import ApiClient, RoundFailure, _save_assets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="https://api.autismteachingcopilot.com")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--target",
        action="append",
        required=True,
        help="Synthetic material_id:visual_id pair; repeat at most three times.",
    )
    parser.add_argument("--confirm-paid-ai", action="store_true")
    args = parser.parse_args()

    if not args.confirm_paid_ai:
        raise RoundFailure("Refusing to run without --confirm-paid-ai")
    if len(args.target) > 3:
        raise RoundFailure("At most three paid visual retries are allowed per run")
    token = args.token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise RoundFailure("Token file is empty")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    client = ApiClient(args.api_base, token, timeout=240)

    results = []
    materials = []
    for target in args.target:
        material_id, separator, visual_id = target.partition(":")
        if not separator or not material_id or not visual_id:
            raise RoundFailure("Each --target must be material_id:visual_id")
        material = client.request(
            "POST",
            f"/api/v2/generated-materials/{material_id}/visuals/{visual_id}/regenerate",
        )
        visual = next(
            (
                item
                for item in (material.get("visualAssetPlan") or {}).get(
                    "visualItems", []
                )
                if item.get("id") == visual_id
            ),
            None,
        )
        if visual is None:
            raise RoundFailure("Regenerated material omitted the requested visual")
        materials.append(material)
        results.append(
            {
                "materialId": material_id,
                "visualId": visual_id,
                "assetId": visual.get("assetId"),
                "status": visual.get("status"),
                "required": visual.get("required"),
            }
        )

    assets = _save_assets(client, materials, args.output_dir)
    report = {
        "schemaVersion": 1,
        "synthetic": True,
        "paidAiConfirmed": True,
        "automaticApproval": False,
        "results": results,
        "assets": assets,
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"PASS: regenerated {len(results)} visual(s); approval still required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
