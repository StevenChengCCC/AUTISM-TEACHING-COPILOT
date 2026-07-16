from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import SkillConfigurationError
from app.skills.models import QualityRule, SkillDefinition, SkillManifest


_SAFE_SEGMENT = re.compile(r"^[a-z][a-z0-9_]*$")
_SAFE_VERSION = re.compile(r"^v[1-9][0-9]*$")


class SkillLoader:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parent

    def load(self, skill_id: str, version: str) -> SkillDefinition:
        if not _SAFE_SEGMENT.fullmatch(skill_id) or not _SAFE_VERSION.fullmatch(
            version
        ):
            raise SkillConfigurationError(
                "The configured AI skill ID or version is invalid."
            )
        skill_dir = self.root / skill_id / version
        manifest_path = skill_dir / "manifest.yaml"
        if not manifest_path.is_file():
            raise SkillConfigurationError(
                f"Required AI skill {skill_id}:{version} is not installed."
            )
        try:
            raw_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest = SkillManifest.model_validate(raw_manifest)
        except (OSError, yaml.YAMLError, PydanticValidationError) as exc:
            raise SkillConfigurationError(
                f"AI skill {skill_id}:{version} has an invalid manifest."
            ) from exc
        if manifest.skill_id != skill_id or manifest.version != version:
            raise SkillConfigurationError(
                f"AI skill {skill_id}:{version} manifest identity does not match its path."
            )

        allowed = {"system.md", "task.md", "quality_rules.yaml", "examples.json"}
        if any(component not in allowed for component in manifest.prompt_components):
            raise SkillConfigurationError(
                f"AI skill {skill_id}:{version} declares an unsupported prompt component."
            )
        missing = [
            component
            for component in manifest.prompt_components
            if not (skill_dir / component).is_file()
        ]
        if missing:
            raise SkillConfigurationError(
                f"AI skill {skill_id}:{version} is missing a required prompt component."
            )
        if (
            "system.md" not in manifest.prompt_components
            or "quality_rules.yaml" not in manifest.prompt_components
        ):
            raise SkillConfigurationError(
                f"AI skill {skill_id}:{version} must declare system and quality components."
            )
        try:
            system_prompt = (
                (skill_dir / "system.md").read_text(encoding="utf-8").strip()
            )
            task_path = skill_dir / "task.md"
            task_prompt = (
                task_path.read_text(encoding="utf-8").strip()
                if "task.md" in manifest.prompt_components
                else None
            )
            quality_raw = yaml.safe_load(
                (skill_dir / "quality_rules.yaml").read_text(encoding="utf-8")
            )
            rules = tuple(
                QualityRule.model_validate(item) for item in quality_raw["rules"]
            )
            examples: tuple[str, ...] = ()
            if "examples.json" in manifest.prompt_components:
                raw_examples = json.loads(
                    (skill_dir / "examples.json").read_text(encoding="utf-8")
                )
                if not isinstance(raw_examples, list):
                    raise ValueError("examples must be a list")
                examples = tuple(
                    json.dumps(item, sort_keys=True, separators=(",", ":"))
                    for item in raw_examples
                )
        except (
            OSError,
            KeyError,
            TypeError,
            ValueError,
            yaml.YAMLError,
            PydanticValidationError,
        ) as exc:
            raise SkillConfigurationError(
                f"AI skill {skill_id}:{version} contains an invalid prompt component."
            ) from exc
        if (
            not system_prompt
            or not rules
            or ("task.md" in manifest.prompt_components and not task_prompt)
        ):
            raise SkillConfigurationError(
                f"AI skill {skill_id}:{version} contains an empty required component."
            )
        return SkillDefinition(manifest, system_prompt, task_prompt, rules, examples)
