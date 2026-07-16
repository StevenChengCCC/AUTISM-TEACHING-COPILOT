from __future__ import annotations

from pathlib import Path

from app.core.config import Settings, settings
from app.core.exceptions import SkillConfigurationError
from app.skills.loader import SkillLoader
from app.skills.models import SkillDefinition


class SkillRegistry:
    def __init__(
        self,
        active_versions: dict[str, str],
        loader: SkillLoader | None = None,
    ) -> None:
        self._active_versions = dict(active_versions)
        self._loader = loader or SkillLoader()
        self._cache: dict[tuple[str, str], SkillDefinition] = {}

    def get(self, skill_id: str, version: str | None = None) -> SkillDefinition:
        selected = version or self._active_versions.get(skill_id)
        if not selected:
            raise SkillConfigurationError(
                f"No active version is configured for required AI skill {skill_id}."
            )
        key = (skill_id, selected)
        if key not in self._cache:
            self._cache[key] = self._loader.load(*key)
        return self._cache[key]

    def validate_required(self) -> tuple[SkillDefinition, ...]:
        return tuple(self.get(skill_id) for skill_id in self._active_versions)

    def active_metadata(self) -> list[dict[str, object]]:
        return [
            {
                "skillId": definition.manifest.skill_id,
                "version": definition.manifest.version,
                "promptTemplateVersion": definition.manifest.prompt_template_version,
                "teacherReviewRequired": definition.manifest.teacher_review_required,
            }
            for definition in self.validate_required()
        ]


def build_skill_registry(config: Settings = settings) -> SkillRegistry:
    root = Path(config.SKILL_ROOT).expanduser() if config.SKILL_ROOT else None
    return SkillRegistry(config.active_skill_versions, SkillLoader(root))


_default_registry: SkillRegistry | None = None


def get_skill_registry(config: Settings = settings) -> SkillRegistry:
    global _default_registry
    if config is settings:
        if _default_registry is None:
            _default_registry = build_skill_registry(config)
        return _default_registry
    return build_skill_registry(config)
