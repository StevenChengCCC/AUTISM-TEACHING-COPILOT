from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SkillManifest(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    skill_id: str = Field(alias="skillId", min_length=1)
    version: str = Field(min_length=1)
    status: Literal["draft", "active", "deprecated"]
    intended_use: tuple[str, ...] = Field(alias="intendedUse", min_length=1)
    prohibited_use: tuple[str, ...] = Field(alias="prohibitedUse", min_length=1)
    input_schema_version: str = Field(alias="inputSchemaVersion", min_length=1)
    output_schema_version: str = Field(alias="outputSchemaVersion", min_length=1)
    prompt_template_version: str = Field(alias="promptTemplateVersion", min_length=1)
    evaluator_version: str = Field(alias="evaluatorVersion", min_length=1)
    teacher_review_required: bool = Field(alias="teacherReviewRequired")
    source_review_status: Literal["pending", "reviewed", "approved"] = Field(
        alias="sourceReviewStatus"
    )
    prompt_components: tuple[str, ...] = Field(alias="promptComponents", min_length=1)


class QualityRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    severity: Literal["low", "medium", "high"] = "medium"


@dataclass(frozen=True)
class SkillDefinition:
    manifest: SkillManifest
    system_prompt: str
    task_prompt: str | None
    quality_rules: tuple[QualityRule, ...]
    examples: tuple[str, ...]


GenerationStatus = Literal[
    "ready", "provider_failure", "invalid_output", "retry_required", "local_mock"
]
OutputSource = Literal["provider", "local_mock", "mock_fallback"]


class GenerationMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    status: GenerationStatus
    provider: str
    model: str
    skill_id: str = Field(alias="skillId")
    skill_version: str = Field(alias="skillVersion")
    prompt_template_version: str = Field(alias="promptTemplateVersion")
    input_schema_version: str = Field(alias="inputSchemaVersion")
    output_schema_version: str = Field(alias="outputSchemaVersion")
    evaluator_version: str = Field(alias="evaluatorVersion")
    generated_at: str = Field(alias="generatedAt")
    output_source: OutputSource = Field(alias="outputSource")
    teacher_review_required: bool = Field(alias="teacherReviewRequired")

    @classmethod
    def from_skill(
        cls,
        skill: SkillDefinition,
        *,
        status: GenerationStatus,
        provider: str,
        model: str,
        output_source: OutputSource,
    ) -> "GenerationMetadata":
        manifest = skill.manifest
        return cls(
            status=status,
            provider=provider,
            model=model,
            skillId=manifest.skill_id,
            skillVersion=manifest.version,
            promptTemplateVersion=manifest.prompt_template_version,
            inputSchemaVersion=manifest.input_schema_version,
            outputSchemaVersion=manifest.output_schema_version,
            evaluatorVersion=manifest.evaluator_version,
            generatedAt=datetime.now(timezone.utc).isoformat(),
            outputSource=output_source,
            teacherReviewRequired=manifest.teacher_review_required,
        )


@dataclass(frozen=True)
class PromptEnvelope:
    system_instructions: str
    user_input: str
    skill: SkillDefinition
    output_contract: dict[str, Any]
