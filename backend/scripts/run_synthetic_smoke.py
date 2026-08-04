#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.services.v2_synthetic_smoke_service import (  # noqa: E402
    V2SyntheticSmokeService,
    render_synthetic_smoke_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic synthetic readiness corpus"
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output/readiness")
    args = parser.parse_args()
    report = V2SyntheticSmokeService(BACKEND).run()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "synthetic-smoke.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "synthetic-smoke.md").write_text(
        render_synthetic_smoke_markdown(report), encoding="utf-8"
    )
    print(f"{report['overallStatus']}: {report['caseCount']} synthetic cases")
    return 0 if report["overallStatus"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
