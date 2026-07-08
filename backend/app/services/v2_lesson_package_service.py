from __future__ import annotations

from app.core.exceptions import NotFoundError, SafetyDeferralError, ValidationError
from app.integrations.ai_provider import V2AIProvider, get_v2_ai_provider
from app.schemas.v2_dto import (
    GeneratedMaterial,
    GeneratedMaterialDto,
    LessonDesignDraft,
    LessonDesignDraftDto,
    LessonPackage,
    LessonPackageDto,
    PrintLayout,
    TeachingStep,
    TeachingStepDto,
)
from app.services.v2_repositories import V2Repositories, repositories
from app.services.v2_safety_harness_service import V2SafetyHarnessService
from app.services.v2_standards_skill_service import V2StandardsSkillService


class V2LessonPackageService:
    def __init__(self, repos: V2Repositories = repositories, ai: V2AIProvider | None = None, safety: V2SafetyHarnessService | None = None, standards: V2StandardsSkillService | None = None):
        self.repos = repos
        self.ai = ai or get_v2_ai_provider()
        self.safety = safety or V2SafetyHarnessService()
        self.standards = standards or V2StandardsSkillService()

    def get(self, package_id: str) -> LessonPackage:
        package = self.repos.packages.get(package_id)
        if not package:
            raise NotFoundError("Lesson package not found")
        return package

    def generate(self, draft: LessonDesignDraft) -> LessonPackage:
        if not draft.goal_text or not draft.selected_materials:
            raise ValidationError("Confirmed goal and materials are required before generation")
        package_id = self.repos.next_id("package")
        lesson_brief = self.ai.polish_lesson_brief(draft)
        safety_report = self.safety.review(draft, lesson_brief)
        if not safety_report.passed:
            raise SafetyDeferralError({"message": "Lesson requires safety review before generation.", "requires_bcba": True, "checks": [item.model_dump(mode="json", by_alias=True) for item in safety_report.checks]})
        standards_report = self.standards.evaluate(draft)
        materials = self._build_materials(package_id, draft.selected_materials)
        package = LessonPackage(
            id=package_id,
            learner_id=draft.learner_id,
            draft_id=draft.id,
            goal=draft.goal_text,
            duration=draft.duration,
            theme=draft.theme,
            lesson_brief=lesson_brief,
            teaching_flow=self._build_flow(),
            materials=materials,
            summary_template="Note what worked, prompt level, regulation, generalization, and next steps.",
            safety_report=safety_report,
            standards_report=standards_report,
        )
        self.repos.packages.save(package)
        for material in materials:
            self.repos.materials.save(material)
        return package

    def generate_product(self, draft: LessonDesignDraftDto) -> LessonPackageDto:
        """Run the product package pipeline through provider, safety, and skills."""

        if not draft.goalText.strip() or not draft.selectedMaterials:
            raise ValidationError(
                "Confirmed goal and materials are required before generation"
            )

        package_id = self.repos.next_id("package")
        generated_content = self.ai.generate_lesson_package(draft)
        teaching_flow = self._build_product_flow()
        materials = self._build_product_materials(package_id)
        safety_review = self.safety.review_product(draft, generated_content)
        standards_checks = self.standards.evaluate_product(draft, materials)

        package = LessonPackageDto(
            id=package_id,
            learnerId=draft.learnerId,
            draftId=draft.id,
            goal=draft.goalText,
            duration=draft.duration,
            theme=draft.theme,
            lessonBrief=generated_content["lessonBrief"],
            teachingFlow=teaching_flow,
            materials=materials,
            summaryTemplate=generated_content["summaryTemplate"],
            safetyReview=safety_review,
            standardsChecks=standards_checks,
        )
        self.repos.lesson_packages.save(package)
        for material in materials:
            self.repos.generated_materials.save(material)
        return package

    def get_product(self, package_id: str) -> LessonPackageDto:
        package = self.repos.lesson_packages.get(package_id)
        if not package or not isinstance(package, LessonPackageDto):
            raise NotFoundError("Lesson package not found")
        return package

    def get_product_materials(self, package_id: str) -> list[GeneratedMaterialDto]:
        return self.get_product(package_id).materials

    @staticmethod
    def _build_product_flow() -> list[TeachingStepDto]:
        return [
            TeachingStepDto(id="warm-up", title="Warm-up and motivation", description="Pair the lesson goal with a familiar, motivating activity.", duration="2 min", teacherAction="Show the visual support and offer the preferred vehicle activity.", learnerAction="Attends to the material or explores the preferred item."),
            TeachingStepDto(id="model-request", title="Model asking for help", description="Demonstrate the target phrase during a small, familiar problem.", duration="2 min", teacherAction="Create a small problem, model “help please,” and point to the help card.", learnerAction="Watches, points, approximates, or says the target phrase."),
            TeachingStepDto(id="guided-practice", title="Guided practice with prompts", description="Practice the request across selected scenarios with planned prompt fading.", duration="4 min", teacherAction="Use least-to-most prompting and provide wait time before verbal help.", learnerAction="Practices asking for help with the selected support level."),
            TeachingStepDto(id="independent-opportunity", title="Independent opportunity", description="Create a familiar opportunity and pause before offering support.", duration="2 min", teacherAction="Pause before prompting and create a familiar help-needed moment.", learnerAction="Attempts to request help independently or with a lighter prompt."),
            TeachingStepDto(id="reinforcement-data", title="Reinforcement and data note", description="Reinforce effort and capture small, multidimensional progress signals.", duration="2 min", teacherAction="Reinforce participation, add a token, and record prompt level, independence, and engagement.", learnerAction="Receives reinforcement and transitions with support."),
        ]

    def _build_product_materials(
        self, package_id: str
    ) -> list[GeneratedMaterialDto]:
        definitions = [
            ("visual_card", "Visual Card", {"phrase": "I need help", "visual": "child pointing to a stuck toy car", "instruction": "Show this card before and during practice opportunities."}),
            ("help_card", "Help Card", {"phrase": "Help please", "prompt": "Point, say, or hand the card to ask for help.", "example": "My car is stuck. Help please."}),
            ("token_board", "Token Board", {"instruction": "Earn 5 stars, then choose a reward.", "reward": "Car", "artwork": "Friendly vehicle artwork", "tokens": 5, "teacherNote": "Praise effort and reinforce each appropriate request."}),
            ("data_sheet", "Data Sheet", {"columns": ["Scenario", "Independent", "Prompt level", "Participation", "Regulation", "Notes"], "promptLevels": ["Level 3 full prompt", "Level 2 partial prompt", "Level 1 gesture/visual prompt", "Independent"], "progressSignals": ["Engagement", "Prompt fading", "Generalization attempt", "Participation"]}),
            ("summary_template", "Summary Template", {"prompts": ["What worked?", "What support was needed?", "What small win was observed?", "What is the next small step?"], "parentSummaryFrame": "Today we practiced asking for help. Progress may be small and uneven, but we are watching for independence, prompt fading, participation, and generalization."}),
        ]
        return [
            GeneratedMaterialDto(
                id=self.repos.next_id("material"),
                packageId=package_id,
                type=material_type,
                title=title,
                status="ready",
                content=content,
                printLayout={
                    "pageSize": "Letter",
                    "orientation": "landscape" if material_type == "token_board" else "portrait",
                    "color": "blue",
                },
            )
            for material_type, title, content in definitions
        ]

    @staticmethod
    def _build_flow() -> list[TeachingStep]:
        return [
            TeachingStep(id="warm-up", title="Warm-up", description="Preview the goal and visuals.", duration="2 min", teacher_action="Model the target response.", learner_action="Attend and respond when ready."),
            TeachingStep(id="practice", title="Guided practice", description="Practice in selected scenarios.", duration="6 min", teacher_action="Create opportunities and fade prompts.", learner_action="Practice the target skill."),
            TeachingStep(id="generalize", title="Generalize", description="Use the skill in a new context.", duration="2 min", teacher_action="Offer a natural opportunity.", learner_action="Try the skill with less support."),
        ]

    def _build_materials(self, package_id: str, selected: list[str]) -> list[GeneratedMaterial]:
        definitions = {
            "Visual Cards": ("visual_card", "Visual Card", {"instruction": "I need help", "artwork": "Communication prompt"}),
            "Token Board": ("token_board", "Token Board", {"instruction": "Earn 5 stars, then get a reward!", "reward": "Car", "tokens": 5}),
            "Data Sheet": ("data_sheet", "Data Sheet", {"columns": ["Scenario", "Independent", "Prompted", "Notes"]}),
            "Summary Template": ("summary_template", "Summary Template", {"instruction": "Record what worked and next steps."}),
        }
        names = list(dict.fromkeys([*selected, "Summary Template"]))
        result: list[GeneratedMaterial] = []
        for name in names:
            material_type, title, content = definitions.get(name, ("help_card", name, {"instruction": name}))
            result.append(GeneratedMaterial(id=self.repos.next_id("material"), package_id=package_id, type=material_type, title=title, content=content, print_layout=PrintLayout(orientation="landscape" if material_type == "token_board" else "portrait")))
        return result
