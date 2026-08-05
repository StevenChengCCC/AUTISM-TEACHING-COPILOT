#!/usr/bin/env python3
"""Record explicit human review for one fully synthetic staging package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_paid_staging_quality_round import ApiClient, RoundFailure


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="https://api.autismteachingcopilot.com")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--package-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-human-review", action="store_true")
    args = parser.parse_args()

    if not args.confirm_human_review:
        raise RoundFailure("Refusing approval without --confirm-human-review")
    token = args.token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise RoundFailure("Token file is empty")
    client = ApiClient(args.api_base, token, timeout=180)
    package = client.request(
        "GET", f"/api/v2/lesson-packages/{args.package_id}"
    )

    reviewed_visuals = []
    reviewed_materials = []
    for material in package.get("materials", []):
        material_id = str(material["id"])
        for visual in (material.get("visualAssetPlan") or {}).get(
            "visualItems", []
        ):
            visual_id = str(visual["id"])
            client.request(
                "POST",
                f"/api/v2/generated-materials/{material_id}/visuals/{visual_id}/review",
                {"action": "approve"},
            )
            reviewed_visuals.append(visual_id)
        client.request(
            "POST", f"/api/v2/generated-materials/{material_id}/review"
        )
        approved = client.request(
            "POST", f"/api/v2/generated-materials/{material_id}/approve"
        )
        reviewed_materials.append(
            {
                "materialId": material_id,
                "revision": (approved.get("materialSpec") or {}).get("revision"),
                "status": approved.get("status"),
            }
        )

    current = client.request(
        "GET", f"/api/v2/lesson-packages/{args.package_id}"
    )
    approved_package = client.request(
        "POST",
        f"/api/v2/lesson-packages/{args.package_id}/approve",
        {
            "expectedVersion": current["version"],
            "reason": "Human-reviewed synthetic staging quality acceptance",
        },
    )
    readiness = client.request(
        "GET", f"/api/v2/lesson-packages/{args.package_id}/print-readiness"
    )
    if not readiness.get("ready"):
        raise RoundFailure("Approval completed but canonical readiness is blocked")

    report = {
        "schemaVersion": 1,
        "synthetic": True,
        "humanReviewConfirmed": True,
        "packageId": args.package_id,
        "packageRevision": approved_package.get("version"),
        "packageStatus": approved_package.get("status"),
        "reviewedVisualCount": len(reviewed_visuals),
        "reviewedVisualIds": reviewed_visuals,
        "reviewedMaterials": reviewed_materials,
        "readiness": {
            "ready": readiness.get("ready"),
            "blockerCount": len(readiness.get("blockers", [])),
            "rendererVersion": readiness.get("rendererVersion"),
            "manifestCompatible": readiness.get("manifestCompatible"),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"PASS: approved {len(reviewed_materials)} materials and "
        f"{len(reviewed_visuals)} visual slots; readiness=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
