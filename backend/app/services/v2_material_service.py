from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.schemas.v2_dto import (
    GeneratedMaterial,
    GeneratedMaterialDto,
    ImageAssetDto,
    LessonPackageDto,
    LessonPackageExportJobDto,
    LessonPackageExportRequest,
    LessonDesignDraftDto,
    LessonDraftMaterialAttachRequest,
    MaterialLibraryItem,
    MaterialLibraryCreateRequest,
    MaterialLibraryItemDto,
    MaterialQuickEditRequest,
    MaterialUpdate,
    MaterialUpdateRequest,
    MaterialRequestDecisionValue,
    MaterialRequestItem,
    TeacherDecision,
    VisualAssetPlan,
    utc_now,
)
from app.services.v2_repositories import V2Repositories, repositories
from app.services.v2_material_spec_service import V2MaterialSpecService
from app.services.v2_safety_harness_service import V2SafetyHarnessService
from app.services.v2_visual_asset_plan_service import V2VisualAssetPlanService


class V2MaterialService:
    def __init__(self, repos: V2Repositories = repositories):
        self.repos = repos

    def list_library(self) -> list[MaterialLibraryItem]:
        return self.repos.library.list()

    def list_library_dtos(self) -> list[MaterialLibraryItemDto]:
        return [self._library_to_dto(item) for item in self.list_library()]

    def create_library_item(
        self, payload: MaterialLibraryCreateRequest
    ) -> MaterialLibraryItemDto:
        item = MaterialLibraryItem(
            id=self.repos.next_id("library"),
            title=payload.title,
            type=payload.type,
            thumbnail_label=payload.thumbnailLabel,
            source=payload.source,
            reusable=payload.reusable,
            configuration=payload.configuration,
            compatible_goal_terms=payload.compatibleGoalTerms,
            compatible_profile_factor_ids=payload.compatibleProfileFactorIds,
            created_at=utc_now(),
        )
        return self._library_to_dto(self.repos.materials_library.save(item))

    def duplicate_library_item(self, material_id: str) -> MaterialLibraryItemDto:
        source = self.repos.materials_library.get(material_id)
        if not source or not isinstance(source, MaterialLibraryItem):
            raise NotFoundError("Material library item not found")
        duplicate = source.model_copy(
            update={
                "id": self.repos.next_id("library"),
                "title": f"{source.title} Copy",
                "created_at": utc_now(),
            }
        )
        return self._library_to_dto(self.repos.materials_library.save(duplicate))

    def attach_to_lesson_draft(
        self, draft_id: str, payload: LessonDraftMaterialAttachRequest
    ) -> LessonDesignDraftDto:
        material = self.repos.materials_library.get(payload.materialId)
        if not material or not isinstance(material, MaterialLibraryItem):
            raise NotFoundError("Material library item not found")
        chat = next(
            (
                conversation
                for conversation in self.repos.conversations.list()
                if conversation.draft.id == draft_id
            ),
            None,
        )
        if not chat:
            raise NotFoundError("Lesson draft not found")
        if material.title not in chat.draft.selected_materials:
            chat.draft.selected_materials.append(material.title)
        if material.compatible_goal_terms and not any(
            term.casefold() in chat.draft.goal_text.casefold()
            for term in material.compatible_goal_terms
        ):
            raise ConflictError(
                "This library material is not compatible with the current goal. Review or change the goal before reuse."
            )
        prior = next(
            (item for item in chat.draft.decisions if item.field == "material_requests"),
            None,
        )
        existing_items = (
            list(prior.value.materials)
            if prior and isinstance(prior.value, MaterialRequestDecisionValue)
            else []
        )
        existing_items = [
            item for item in existing_items if item.library_material_id != material.id
        ]
        existing_items.append(
            MaterialRequestItem(
                requestId=f"library-{material.id}",
                materialType=material.type,
                customLabel=material.title,
                purpose="Teacher-selected reusable library material",
                profileFactorIds=material.compatible_profile_factor_ids,
                libraryMaterialId=material.id,
                libraryMaterialVersion=material.version,
                libraryConfiguration=material.configuration,
                origin="library_reused",
            )
        )
        decision = TeacherDecision(
            id=prior.id if prior else f"decision-{chat.draft.id}-material_requests",
            field="material_requests",
            source="teacher_selected",
            optionIds=[item.request_id for item in existing_items],
            profileFactorIds=list(dict.fromkeys(
                factor for item in existing_items for factor in item.profile_factor_ids
            )),
            value=MaterialRequestDecisionValue(materials=existing_items),
            reason="Teacher selected a complete versioned library material.",
            affects=["materials", "printable_package"],
            revision=(prior.revision + 1 if prior else 1),
        )
        chat.draft.decisions = [
            item for item in chat.draft.decisions if item.field != "material_requests"
        ] + [decision]
        self.repos.conversations.save(chat)
        return LessonDesignDraftDto.model_validate(
            chat.draft.model_dump(mode="json", by_alias=True)
        )

    def list_generated(self, package_id: str) -> list[GeneratedMaterial]:
        if not self.repos.packages.get(package_id):
            raise NotFoundError("Lesson package not found")
        return self.repos.materials.for_package(package_id)

    def update(self, material_id: str, payload: MaterialUpdate) -> GeneratedMaterial:
        material = self.repos.materials.get(material_id)
        if not material:
            raise NotFoundError("Generated material not found")
        updated = material.model_copy(update=payload.model_dump(exclude_none=True))
        return self.repos.materials.save(updated)

    def list_generated_dtos(self, package_id: str) -> list[GeneratedMaterialDto]:
        package = self._get_product_package(package_id)
        materials = [
            material
            for material in self.repos.generated_materials.for_package(package_id)
            if isinstance(material, GeneratedMaterialDto)
        ]
        return materials or package.materials

    def update_generated(
        self, material_id: str, payload: MaterialUpdateRequest
    ) -> GeneratedMaterialDto:
        material = self._get_generated_dto(material_id)
        updated = self._prepare_material_edit(material, {
            "title": payload.title,
            "content": payload.content,
            "printLayout": payload.printLayout,
            **({"version": payload.expectedVersion} if payload.expectedVersion is not None else {}),
        })
        return self._save_generated(updated)

    def review_generated(self, material_id: str) -> GeneratedMaterialDto:
        """Record that the teacher opened and reviewed this exact revision."""

        material = self._get_generated_dto(material_id)
        if material.materialSchemaVersion != 1 or material.materialSpec is None:
            # Historical schema-v0 packages retain their original compatibility
            # policy and do not gain a synthetic typed approval lineage.
            return material
        package = self._get_product_package(material.packageId)
        if package.lessonSpec is None:
            raise ConflictError("The current material has no LessonSpec validation boundary")
        validator = V2MaterialSpecService()
        semantic = validator.validate(material.materialSpec, package.lessonSpec, material.content)
        safety = validator.validate_safety(material.materialSpec, package.lessonSpec, semantic, material.content)
        if semantic.status != "passed" or safety.status != "passed":
            raise ConflictError("This material revision must pass semantic and safety validation before review")
        spec = material.materialSpec.model_copy(update={
            "semantic_validation": semantic,
            "safety_validation": safety,
            "approval": material.materialSpec.approval.model_copy(update={
                "status": "reviewed",
                "reviewed_revision": material.materialSpec.revision,
                "approved_revision": None,
            }),
        })
        return self._save_generated(material.model_copy(update={
            "materialSpec": spec, "status": "teacher_review_needed",
        }))

    def approve_generated(self, material_id: str) -> GeneratedMaterialDto:
        material = self._get_generated_dto(material_id)
        package = self._get_product_package(material.packageId)
        if package.safetyReview and package.safetyReview.status == "blocked":
            raise ConflictError(
                "A material from a safety-blocked package cannot be approved"
            )
        # Package-level instructional checks are reviewed when the teacher
        # approves/exports the complete kit. They must not make an otherwise
        # safe individual card's "Approve for Print" button unusable.
        material_review = V2SafetyHarnessService().review_product(
            self._draft_for_package(package),
            {"materialContent": material.content},
            detected_revision=material.materialSpec.revision if material.materialSpec else material.version,
        )
        if material_review.status == "blocked":
            raise ConflictError(
                "A safety-blocked generated material cannot be approved"
            )
        updates: dict[str, object] = {"status": "approved"}
        if material.materialSchemaVersion == 1 and material.visualAssetPlan is not None:
            if material.materialSpec is None:
                raise ConflictError("The visual plan has no current MaterialSpec boundary")
            planner = V2VisualAssetPlanService()
            planner.require_valid(material.visualAssetPlan, material.materialSpec)
            blockers = planner.approval_blockers(material.visualAssetPlan)
            if blockers:
                raise ConflictError(
                    "Required instructional visuals are missing: " + "; ".join(blockers),
                )
        if material.materialSpec is not None:
            if package.lessonSpec is None:
                raise ConflictError("The current material has no LessonSpec validation boundary")
            validator = V2MaterialSpecService()
            semantic = validator.validate(material.materialSpec, package.lessonSpec, material.content)
            safety = validator.validate_safety(material.materialSpec, package.lessonSpec, semantic, material.content)
            approval = material.materialSpec.approval
            if semantic.status != "passed" or safety.status != "passed":
                raise ConflictError("This material revision has not passed semantic and safety validation")
            if approval.status != "reviewed" or approval.reviewed_revision != material.materialSpec.revision:
                raise ConflictError("Open and review this material revision before approving it")
            updates["materialSpec"] = material.materialSpec.model_copy(
                update={
                    "semantic_validation": semantic,
                    "safety_validation": safety,
                    "approval": material.materialSpec.approval.model_copy(
                        update={
                            "status": "approved",
                            "reviewed_revision": material.materialSpec.revision,
                            "approved_revision": material.materialSpec.revision,
                        }
                    )
                }
            )
        approved = self._save_generated(material.model_copy(update=updates))
        self._sync_approved_material_to_library(approved)
        return approved

    def _sync_approved_material_to_library(
        self, material: GeneratedMaterialDto
    ) -> None:
        """Expose the current approved revision on the Materials page.

        The library projection contains only minimized reusable metadata. The
        learner code, profile evidence, signed URLs, and printable bytes remain
        outside the library record.
        """

        categories = {
            "break_card": "Help Cards",
            "first_then_board": "Visual Cards",
            "token_board": "Token Boards",
            "data_sheet": "Data Sheets",
            "summary_template": "Summary Templates",
        }
        library_id = f"generated-{material.id}"
        current = self.repos.materials_library.get(library_id)
        revision = (
            material.materialSpec.revision
            if material.materialSpec is not None
            else material.version
        )
        item = MaterialLibraryItem(
            id=library_id,
            title=material.title,
            type=categories.get(material.type, "Visual Cards"),
            thumbnailLabel=material.title,
            source="generated",
            reusable=True,
            createdAt=(current.created_at if current else utc_now()),
            configuration={
                "materialType": material.type,
                "generatedMaterialId": material.id,
                "packageId": material.packageId,
                "materialRevision": revision,
            },
            compatibleGoalTerms=["break"],
            compatibleProfileFactorIds=(
                material.materialSpec.profile_factor_ids
                if material.materialSpec is not None
                else []
            ),
            version=(current.version if current else 1),
        )
        self.repos.materials_library.save(item)

    def quick_edit_generated(
        self, material_id: str, payload: MaterialQuickEditRequest
    ) -> GeneratedMaterialDto:
        material = self._get_generated_dto(material_id)
        content = dict(material.content)
        if payload.action == "simplify_wording":
            original = str(
                content.get("instruction")
                or content.get("direction")
                or content.get("phrase")
                or ""
            ).strip()
            if original:
                first_sentence = original.split(".", 1)[0].strip()
                words = first_sentence.split()
                shortened = " ".join(words[:12]).rstrip(",;:")
                content["instruction"] = (
                    f"{shortened}." if shortened else original
                )
            else:
                content["instruction"] = "Follow the visual, then try the skill."
        elif payload.action == "regenerate_artwork":
            content["artwork"] = "Updated classroom artwork"
        else:
            current = str(content.get("reward") or "").lower()
            rewards = ["Choice activity", "Movement break", "Preferred item"]
            content["reward"] = next(
                (reward for reward in rewards if reward.lower() != current),
                rewards[0],
            )
        return self._save_generated(self._prepare_material_edit(material, {"content": content}))

    def set_image_generation_status(
        self, material_id: str, status: str, message: str | None = None
    ) -> GeneratedMaterialDto:
        material = self._get_generated_dto(material_id)
        content = dict(material.content)
        content["imageGenerationStatus"] = status
        if message:
            content["imageGenerationMessage"] = message
        else:
            content.pop("imageGenerationMessage", None)
        # Queue state is execution metadata, not a semantic material edit. Keep
        # the current MaterialSpec revision and VisualAssetPlan intact.
        return self._save_generated(material.model_copy(update={"content": content}))

    def attach_image_asset_if_exists(
        self, material_id: str, asset: ImageAssetDto
    ) -> bool:
        material = self.repos.generated_materials.get(material_id)
        if not material:
            return False
        content = dict(material.content)
        content.update(
            {
                "imageConcept": asset.concept,
                "imageAssetId": asset.id,
                "imageUrl": asset.imageUrl or asset.thumbnailUrl,
                "imageBase64": None if asset.imageUrl else asset.imageBase64,
                "imageAltText": asset.altText,
                "imageSourceType": asset.sourceType,
                "imageLicenseInfo": asset.licenseInfo,
                "imageSafetyStatus": asset.safetyStatus,
                "imageGenerationStatus": (
                    "ready"
                    if asset.sourceType in {"generated", "internal"}
                    else (
                        "needs_review"
                        if asset.sourceType in {"pexels", "pixabay", "unsplash"}
                        else "failed"
                    )
                ),
            }
        )
        content.pop("imageGenerationMessage", None)
        if isinstance(material, GeneratedMaterialDto):
            try:
                # Asset attachment changes execution metadata only; it must not
                # rebuild the semantic spec or discard the current visual plan.
                updated = material.model_copy(update={
                    "content": content,
                    "status": "teacher_review_needed",
                })
                self._save_generated(updated)
            except NotFoundError:
                # Asset approval must remain successful even for an orphaned
                # in-memory material created during development.
                self.repos.generated_materials.save(material.model_copy(
                    update={"content": content, "status": "teacher_review_needed"}
                ))
        else:
            self.repos.generated_materials.save(material)
        return True

    def attach_visual_assets(
        self,
        material_id: str,
        visual_items: list[dict],
        *,
        overall_status: str,
    ) -> GeneratedMaterialDto:
        """Persist a material's complete visual asset set.

        Top-level image fields are retained as a compatibility thumbnail, while
        ``visualItems`` is the source of truth for material-specific layout.
        """

        material = self._get_generated_dto(material_id)
        content = dict(material.content)
        content["visualItems"] = visual_items
        content["imageGenerationStatus"] = overall_status
        first = next(
            (
                item
                for item in visual_items
                if isinstance(item, dict)
                and (item.get("imageUrl") or item.get("imageBase64"))
            ),
            None,
        )
        if first:
            content.update(
                {
                    "imageConcept": first.get("concept"),
                    "imageAssetId": first.get("imageAssetId"),
                    "imageUrl": first.get("imageUrl"),
                    "imageBase64": first.get("imageBase64"),
                    "imageAltText": first.get("imageAltText"),
                    "imageSourceType": first.get("imageSourceType"),
                    "imageLicenseInfo": first.get("imageLicenseInfo"),
                    "imageSafetyStatus": first.get("imageSafetyStatus"),
                }
            )
        if overall_status not in {"failed", "processing", "pending"}:
            content.pop("imageGenerationMessage", None)
        return self._save_generated(material.model_copy(update={
            "content": content,
            "status": "teacher_review_needed",
        }))

    def attach_visual_plan(
        self, material_id: str, plan: VisualAssetPlan, *, overall_status: str
    ) -> GeneratedMaterialDto:
        """Persist visual execution without changing MaterialSpec semantics."""

        material = self._get_generated_dto(material_id)
        if material.materialSpec is None:
            raise ConflictError("A typed visual plan requires a MaterialSpec")
        planner = V2VisualAssetPlanService()
        planner.require_valid(plan, material.materialSpec)
        renderer_items = planner.to_renderer_items(plan)
        for rendered, planned in zip(renderer_items, plan.visual_items, strict=True):
            asset_id = planned.asset_id
            if not asset_id or asset_id.startswith("deterministic:"):
                continue
            asset = self.repos.image_assets.get(asset_id)
            if not asset:
                continue
            rendered.update({
                "imageAssetId": asset.id,
                "imageUrl": asset.imageUrl or asset.thumbnailUrl,
                "imageBase64": None if asset.imageUrl else asset.imageBase64,
                "imageAltText": planned.alt_text,
                "imageSourceType": asset.sourceType,
                "imageLicenseInfo": asset.licenseInfo,
                "imageSafetyStatus": asset.safetyStatus,
                "generationStatus": planned.status,
            })
        content = dict(material.content)
        content["visualItems"] = renderer_items
        content["imageGenerationStatus"] = overall_status
        first = next((item for item in renderer_items if item.get("imageUrl") or item.get("imageBase64")), None)
        if first:
            content.update({
                "imageConcept": first.get("concept"),
                "imageAssetId": first.get("imageAssetId"),
                "imageUrl": first.get("imageUrl"),
                "imageBase64": first.get("imageBase64"),
                "imageAltText": first.get("imageAltText"),
                "imageSourceType": first.get("imageSourceType"),
                "imageLicenseInfo": first.get("imageLicenseInfo"),
                "imageSafetyStatus": first.get("imageSafetyStatus"),
            })
        requests = []
        for request in material.materialSpec.visual_asset_requests:
            planned = next((item for item in plan.visual_items if item.id == request.id), None)
            requests.append(request.model_copy(update={
                "status": (
                    "ready" if planned and (planned.status in {"ready", "needs_review"} or planned.fallback_asset_id)
                    else "failed" if planned and planned.status == "failed"
                    else "requested"
                )
            }))
        spec = material.materialSpec.model_copy(update={
            "visual_asset_requests": requests,
            "approval": material.materialSpec.approval.model_copy(update={
                "status": "not_reviewed", "reviewed_revision": None,
                "approved_revision": None,
            }),
        })
        updated = material.model_copy(update={
            "content": content,
            "visualAssetPlan": plan,
            "materialSpec": spec,
            "status": "teacher_review_needed",
        })
        return self._save_generated(updated)

    def choose_visual_fallback(
        self, material_id: str, visual_item_id: str
    ) -> GeneratedMaterialDto:
        material = self._get_generated_dto(material_id)
        plan = self._require_visual_plan(material, visual_item_id)
        items = []
        for item in plan.visual_items:
            if item.id == visual_item_id:
                if not item.fallback_asset_id:
                    raise ConflictError("This visual has no deterministic fallback")
                item = item.model_copy(update={
                    "asset_id": item.fallback_asset_id,
                    "status": "ready",
                    "review_status": "unreviewed",
                    "design_constraints": {**item.design_constraints, "fallbackVisible": True},
                })
            items.append(item)
        revised = plan.model_copy(update={"visual_items": items})
        return self.attach_visual_plan(material_id, revised, overall_status=self._visual_overall_status(revised))

    def replace_visual_asset(
        self, material_id: str, visual_item_id: str, asset_id: str
    ) -> GeneratedMaterialDto:
        material = self._get_generated_dto(material_id)
        plan = self._require_visual_plan(material, visual_item_id)
        asset = self.repos.image_assets.get(asset_id)
        if not asset or asset.safetyStatus == "blocked":
            raise ConflictError("The replacement asset is missing or safety-blocked")
        items = [
            item.model_copy(update={
                "asset_id": asset.id,
                "status": "ready" if asset.safetyStatus == "ready" else "needs_review",
                "review_status": "unreviewed",
            }) if item.id == visual_item_id else item
            for item in plan.visual_items
        ]
        revised = plan.model_copy(update={"visual_items": items})
        return self.attach_visual_plan(material_id, revised, overall_status=self._visual_overall_status(revised))

    def review_visual(
        self, material_id: str, visual_item_id: str, action: str
    ) -> GeneratedMaterialDto:
        material = self._get_generated_dto(material_id)
        plan = self._require_visual_plan(material, visual_item_id)
        items = []
        for item in plan.visual_items:
            if item.id == visual_item_id:
                if action == "approve":
                    if item.status not in {"ready", "needs_review"} and not item.fallback_asset_id:
                        raise ConflictError("This visual is not ready for review")
                    if item.asset_id:
                        asset = self.repos.image_assets.get(item.asset_id)
                        if asset and asset.safetyStatus != "blocked":
                            self.repos.image_assets.save(
                                asset.model_copy(
                                    update={
                                        "approved": True,
                                        "safetyStatus": "ready",
                                    }
                                )
                            )
                    item = item.model_copy(update={"review_status": "approved"})
                else:
                    item = item.model_copy(update={
                        "review_status": "rejected", "status": "failed",
                        "asset_id": item.fallback_asset_id,
                        "design_constraints": {
                            **item.design_constraints,
                            "fallbackVisible": bool(item.fallback_asset_id),
                        },
                    })
            items.append(item)
        revised = plan.model_copy(update={"visual_items": items})
        return self.attach_visual_plan(material_id, revised, overall_status=self._visual_overall_status(revised))

    @staticmethod
    def _visual_overall_status(plan: VisualAssetPlan) -> str:
        planner = V2VisualAssetPlanService()
        if planner.approval_blockers(plan):
            return "failed"
        if any(item.status in {"failed", "needs_review"} for item in plan.visual_items):
            return "needs_review"
        if any(item.status in {"planned", "generating"} for item in plan.visual_items):
            return "processing"
        return "ready"

    @staticmethod
    def _require_visual_plan(
        material: GeneratedMaterialDto, visual_item_id: str
    ) -> VisualAssetPlan:
        plan = material.visualAssetPlan
        if plan is None:
            raise ConflictError("This material has no typed visual plan")
        if not any(item.id == visual_item_id for item in plan.visual_items):
            raise NotFoundError("Visual item not found")
        return plan

    def create_export_job(
        self, package_id: str, payload: LessonPackageExportRequest
    ) -> LessonPackageExportJobDto:
        from app.services.v2_handoff_export_service import V2HandoffExportService

        return V2HandoffExportService(self.repos).create_for_package(
            package_id, payload
        )

    def _get_generated_dto(self, material_id: str) -> GeneratedMaterialDto:
        material = self.repos.generated_materials.get(material_id)
        if not material or not isinstance(material, GeneratedMaterialDto):
            raise NotFoundError("Generated material not found")
        return material

    def _get_product_package(self, package_id: str) -> LessonPackageDto:
        package = self.repos.lesson_packages.get(package_id)
        if not package or not isinstance(package, LessonPackageDto):
            raise NotFoundError("Lesson package not found")
        return package

    def _save_generated(self, material: GeneratedMaterialDto) -> GeneratedMaterialDto:
        with self.repos.transaction():
            saved = self.repos.generated_materials.save(material)
            package = self._get_product_package(material.packageId)
            package.materials = [
                saved if current.id == saved.id else current
                for current in package.materials
            ]
            if saved.status != "approved" and package.status == "approved":
                package.status = "teacher_review_needed"
            from app.services.v2_lesson_package_service import V2LessonPackageService
            refreshed = V2LessonPackageService(self.repos)._reevaluate_product(package)
            if refreshed.validationStatus == "passed":
                refreshed = refreshed.model_copy(update={"validatedRevision": package.version + 1})
            self.repos.lesson_packages.save(refreshed)
        return saved

    def _prepare_material_edit(
        self, material: GeneratedMaterialDto, updates: dict[str, object]
    ) -> GeneratedMaterialDto:
        """Create a new semantic revision and invalidate its prior approval."""

        candidate = material.model_copy(update={**updates, "status": "teacher_review_needed"})
        if material.materialSchemaVersion != 1 or material.materialSpec is None:
            return candidate
        package = self._get_product_package(material.packageId)
        if package.lessonSpec is None:
            return candidate.model_copy(update={"status": "validation_failed"})
        old_spec = material.materialSpec
        content_payload = updates.get("content")
        typed_content = old_spec.content
        if isinstance(content_payload, dict):
            old_values = old_spec.content.model_dump(mode="json", by_alias=True)
            relevant = {key: value for key, value in content_payload.items() if key in old_values}
            if old_spec.artifact_type == "token_board" and "reward" in content_payload:
                relevant["earnedReward"] = content_payload["reward"]
            if relevant:
                try:
                    typed_content = type(old_spec.content).model_validate({**old_values, **relevant})
                except Exception as exc:
                    raise ValidationError(f"Material edit violates its typed content schema: {exc}") from exc
        revised = old_spec.model_copy(update={
            "revision": old_spec.revision + 1,
            "title": str(updates.get("title", old_spec.title)),
            "content": typed_content,
            "repair_attempts": 0,
            "repair_status": "not_needed",
            "approval": old_spec.approval.model_copy(update={
                "status": "not_reviewed", "reviewed_revision": None,
                "approved_revision": None,
            }),
        })
        validator = V2MaterialSpecService()
        visual_planner = V2VisualAssetPlanService()
        visual_plan = visual_planner.build(revised)
        from app.schemas.v2_dto import MaterialVisualAssetRequest
        visual_requests = [
            MaterialVisualAssetRequest(
                id=item.id,
                purpose=item.instructional_purpose,
                description=str(item.design_constraints.get("concept") or item.visible_label),
                altText=item.alt_text,
                status="ready" if item.status == "ready" else "not_requested",
            )
            for item in visual_plan.visual_items
        ]
        revised = revised.model_copy(update={"visual_asset_requests": visual_requests})
        projection = validator.render_projection(revised, candidate.content)
        projection["visualItems"] = visual_planner.to_renderer_items(visual_plan)
        projection["imageGenerationStatus"] = (
            "not_started"
            if any(item.generation_method == "ai_generated" for item in visual_plan.visual_items)
            else "ready"
        )
        semantic = validator.validate(revised, package.lessonSpec, projection)
        safety = validator.validate_safety(revised, package.lessonSpec, semantic, projection)
        revised = revised.model_copy(update={
            "semantic_validation": semantic, "safety_validation": safety,
        })
        status = (
            "validation_failed" if semantic.status != "passed"
            else "safety_review_needed" if safety.status != "passed"
            else "teacher_review_needed"
        )
        return candidate.model_copy(update={
            "content": projection,
            "materialSpec": revised,
            "visualAssetPlan": visual_plan,
            "status": status,
        })

    @staticmethod
    def _draft_for_package(package: LessonPackageDto) -> LessonDesignDraftDto:
        return LessonDesignDraftDto(
            id=package.draftId,
            learnerId=package.learnerId,
            goalText=package.goal,
            observableResponse=package.observableResponse or package.goal,
            baseline=package.baseline,
            responseLevel=package.responseModality,
            scenarios=(
                package.generalizationPlan.examples
                if package.generalizationPlan
                else []
            ),
            selectedMaterials=[item.title for item in package.materials],
            theme=package.theme,
            duration=package.duration,
            customNotes="",
            promptingStart=(
                package.promptingPlan.startingPrompt if package.promptingPlan else ""
            ),
            promptingLimits=(
                package.promptingPlan.teacherOverride if package.promptingPlan else ""
            ),
            reinforcementPlan=(
                package.reinforcementPlan.selectedSupport
                if package.reinforcementPlan
                else ""
            ),
            errorCorrection=(
                package.errorCorrectionPlan.neutralResponse
                if package.errorCorrectionPlan
                else ""
            ),
            dataCollection="Record response outcome and prompt level",
            generalizationPlan="Teacher-reviewed generalization plan",
        )

    @staticmethod
    def _library_to_dto(item: MaterialLibraryItem) -> MaterialLibraryItemDto:
        return MaterialLibraryItemDto(
            id=item.id,
            title=item.title,
            type=item.type,
            thumbnailLabel=item.thumbnail_label,
            source=item.source,
            reusable=item.reusable,
            createdAt=item.created_at.isoformat(),
            configuration=item.configuration,
            compatibleGoalTerms=item.compatible_goal_terms,
            compatibleProfileFactorIds=item.compatible_profile_factor_ids,
            version=item.version,
        )
