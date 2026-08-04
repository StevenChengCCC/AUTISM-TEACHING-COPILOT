#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from app.services.v2_production_readiness_service import (  # noqa: E402
    V2ProductionReadinessService,
    render_readiness_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only fail-closed production readiness gate"
    )
    parser.add_argument(
        "--environment",
        choices=("development", "test", "staging", "production"),
        default="production",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output/readiness")
    args = parser.parse_args()
    config = Settings(APP_ENV=args.environment)
    report = V2ProductionReadinessService(config, ROOT).evaluate()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "production-readiness.json"
    md_path = args.output_dir / "production-readiness.md"
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_readiness_markdown(report), encoding="utf-8")
    print(f"{report.overallStatus}: {md_path}")
    return 0 if report.overallStatus == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
