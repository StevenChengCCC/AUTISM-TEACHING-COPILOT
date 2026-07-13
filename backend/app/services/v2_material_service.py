from app.core.exceptions import NotFoundError, ValidationError
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
    utc_now,
)
from app.services.v2_repositories import V2Repositories, repositories


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
        updated = material.model_copy(
            update={
                "title": payload.title,
                "content": payload.content,
                "printLayout": payload.printLayout,
            }
        )
        return self._save_generated(updated)

    def approve_generated(self, material_id: str) -> GeneratedMaterialDto:
        material = self._get_generated_dto(material_id)
        return self._save_generated(material.model_copy(update={"status": "approved"}))

    def quick_edit_generated(
        self, material_id: str, payload: MaterialQuickEditRequest
    ) -> GeneratedMaterialDto:
        material = self._get_generated_dto(material_id)
        content = dict(material.content)
        if payload.action == "simplify_wording":
            content["instruction"] = "Ask for help."
        elif payload.action == "regenerate_artwork":
            content["artwork"] = "Updated classroom artwork"
        else:
            content["reward"] = "Choice activity"
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
            }
        )
        updated = material.model_copy(update={"content": content})
        if isinstance(updated, GeneratedMaterialDto):
            try:
                self._save_generated(updated)
            except NotFoundError:
                # Asset approval must remain successful even for an orphaned
                # in-memory material created during development.
                self.repos.generated_materials.save(updated)
        else:
            self.repos.generated_materials.save(updated)
        return True

    def create_export_job(
        self, package_id: str, payload: LessonPackageExportRequest
    ) -> LessonPackageExportJobDto:
        available = self.list_generated_dtos(package_id)
        available_ids = {material.id for material in available}
        unknown_ids = set(payload.materialIds) - available_ids
        if unknown_ids:
            raise ValidationError("Export includes material IDs outside this package")
        return LessonPackageExportJobDto(
            exportId=f"export-{package_id}-{payload.format}",
            status="ready",
            format=payload.format,
            downloadUrl=f"/mock-downloads/{package_id}.{payload.format}",
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

    def _save_generated(
        self, material: GeneratedMaterialDto
    ) -> GeneratedMaterialDto:
        saved = self.repos.generated_materials.save(material)
        package = self._get_product_package(material.packageId)
        package.materials = [
            saved if current.id == saved.id else current
            for current in package.materials
        ]
        self.repos.lesson_packages.save(package)
        return saved

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
        )
