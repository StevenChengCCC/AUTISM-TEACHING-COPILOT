import { useEffect, useState } from "react";
import { lessonKitApi } from "../api/lessonKitApi";
import { LearnerAvatar } from "../components/Avatar";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { PrintableMaterialCanvas } from "../components/PrintableMaterialCanvas";
import type {
  GeneratedMaterial,
  LearnerProfile,
  LessonPackage,
  MaterialQuickEditAction,
} from "../types";

const imageMaterialTypes = [
  "quantity_cards",
  "number_cards",
  "visual_card",
  "scenario_cards",
  "sequence_cards",
  "social_narrative",
  "core_word_board",
  "visual_schedule",
  "task_analysis_cards",
  "emotion_scale",
  "sorting_page",
  "matching_page",
  "choice_board",
  "first_then_board",
  "help_card",
  "break_card",
  "teacher_cue_card",
  "token_board",
];

function hasCompleteVisualSet(material: GeneratedMaterial): boolean {
  if (!imageMaterialTypes.includes(material.type)) return true;
  const items = material.content.visualItems;
  if (Array.isArray(items) && items.length > 0) {
    return items.every((item) => {
      if (!item || typeof item !== "object") return false;
      const value = item as Record<string, unknown>;
      return (
        Boolean(value.imageUrl || value.imageBase64) &&
        !["pending", "processing", "failed"].includes(
          String(value.generationStatus ?? ""),
        )
      );
    });
  }
  return Boolean(material.content.imageUrl || material.content.imageBase64);
}

function materialIcon(type: string): string {
  if (type === "visual_card") return "▧";
  if (type === "help_card") return "◉";
  if (type === "token_board") return "☆";
  if (type === "data_sheet") return "▦";
  return "▤";
}

export function ReviewPrintableContentPage({
  lessonPackage,
  initialSelectedId = "",
  onBack,
  onFeedback,
}: {
  lessonPackage: LessonPackage | null;
  initialSelectedId?: string;
  onBack: () => void;
  onFeedback: (message: string) => void;
}) {
  const [materials, setMaterials] = useState<GeneratedMaterial[]>([]);
  const [learner, setLearner] = useState<LearnerProfile | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [title, setTitle] = useState("");
  const [instruction, setInstruction] = useState("");
  const [reward, setReward] = useState("Teacher-confirmed reward");
  const [pageSize, setPageSize] = useState<"Letter" | "A4">("Letter");
  const [dirty, setDirty] = useState(false);
  const [imageBusy, setImageBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [localMessage, setLocalMessage] = useState("");

  useEffect(() => {
    if (!lessonPackage) return;
    void Promise.all([
      lessonKitApi.getGeneratedMaterials(lessonPackage.id),
      lessonKitApi.getLearnerById(lessonPackage.learnerId),
    ])
      .then(([items, profile]) => {
        setMaterials(items);
        setLearner(profile);
        setSelectedId(
          items.some((item) => item.id === initialSelectedId)
            ? initialSelectedId
            : (items[0]?.id ?? ""),
        );
      })
      .catch((reason: unknown) => {
        const message =
          reason instanceof Error
            ? reason.message
            : "Printable materials could not be loaded.";
        setLocalMessage(message);
      });
  }, [lessonPackage?.id, initialSelectedId]);

  const selected =
    materials.find((item) => item.id === selectedId) ?? materials[0];
  const imageStateKey = materials
    .map((item) => String(item.content.imageGenerationStatus ?? ""))
    .join("|");

  useEffect(() => {
    if (
      !lessonPackage ||
      !materials.some((item) =>
        ["pending", "processing"].includes(
          String(item.content.imageGenerationStatus ?? ""),
        ),
      )
    ) {
      return;
    }
    let cancelled = false;
    const refresh = async () => {
      try {
        const items = await lessonKitApi.getGeneratedMaterials(lessonPackage.id);
        if (!cancelled) setMaterials(items);
      } catch {
        // Background polling must not make the editor unusable.
      }
    };
    const timer = window.setInterval(() => void refresh(), 3000);
    void refresh();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [lessonPackage?.id, imageStateKey]);

  useEffect(() => {
    if (!selected) return;
    setTitle(selected.title);
    setInstruction(String(selected.content.instruction ?? ""));
    setReward(
      String(selected.content.reward ?? "Teacher-confirmed reward"),
    );
    setPageSize(selected.printLayout.pageSize);
    setDirty(false);
    setLocalMessage("");
  }, [selected?.id, selected?.version]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  if (!lessonPackage) {
    return (
      <section className="v2-empty">
        <h2>No printable content yet</h2>
        <Button onClick={onBack}>Back</Button>
      </section>
    );
  }

  const replaceMaterial = (value: GeneratedMaterial) =>
    setMaterials((current) =>
      current.map((item) => (item.id === value.id ? value : item)),
    );

  const save = async (): Promise<GeneratedMaterial | null> => {
    if (!selected) return null;
    const value = await lessonKitApi.updateGeneratedMaterial(selected.id, {
      title,
      content: {
        ...selected.content,
        instruction,
        ...(selected.type === "token_board" ? { reward } : {}),
      },
      printLayout: {
        ...selected.printLayout,
        pageSize,
      },
    });
    replaceMaterial(value);
    setDirty(false);
    return value;
  };

  const approve = async () => {
    if (!selected || actionBusy) return;
    if (!hasCompleteVisualSet(selected)) {
      setLocalMessage(
        "Finish and review every custom image before approving this material.",
      );
      return;
    }
    setActionBusy(true);
    setLocalMessage("");
    try {
      const saved = dirty ? await save() : selected;
      if (!saved) return;
      const value = await lessonKitApi.approveGeneratedMaterial(saved.id);
      replaceMaterial(value);
      setLocalMessage("Approved for the complete printable PDF.");
      onFeedback(`${value.title} approved for print.`);
    } catch (reason) {
      const message =
        reason instanceof Error
          ? reason.message
          : "This material could not be approved.";
      setLocalMessage(message);
      onFeedback(message);
    } finally {
      setActionBusy(false);
    }
  };

  const quickEdit = async (action: MaterialQuickEditAction) => {
    if (!selected) return;
    setLocalMessage("");
    try {
      if (action === "regenerate_artwork") {
        setImageBusy(true);
        const value = await lessonKitApi.generateGeneratedMaterialImage(
          selected.id,
        );
        replaceMaterial(value);
        onFeedback(
          "New lesson-specific artwork is being created. You can review other pages while it finishes.",
        );
        return;
      }
      const value = await lessonKitApi.quickEditGeneratedMaterial(
        selected.id,
        action,
      );
      replaceMaterial(value);
      onFeedback(`${value.title} updated.`);
    } catch (reason) {
      const message =
        reason instanceof Error
          ? reason.message
          : "The requested edit could not be applied.";
      setLocalMessage(message);
      onFeedback(message);
    } finally {
      if (action === "regenerate_artwork") setImageBusy(false);
    }
  };

  const exportPdf = async () => {
    setActionBusy(true);
    setLocalMessage("");
    try {
      const visualMaterials = materials.filter((item) =>
        imageMaterialTypes.includes(item.type),
      );
      const generating = visualMaterials.find((item) =>
        ["pending", "processing"].includes(
          String(item.content.imageGenerationStatus ?? ""),
        ),
      );
      if (generating) {
        setSelectedId(generating.id);
        setLocalMessage(
          "Custom artwork is still generating. Printing unlocks when every selected visual is ready.",
        );
        return;
      }
      const missing = visualMaterials.find(
        (item) => !hasCompleteVisualSet(item),
      );
      if (missing) {
        setSelectedId(missing.id);
        setLocalMessage(
          `${missing.title} is missing one or more classroom images.`,
        );
        return;
      }
      const approvedMaterials: GeneratedMaterial[] = [];
      for (const material of materials) {
        approvedMaterials.push(
          material.status === "approved"
            ? material
            : await lessonKitApi.approveGeneratedMaterial(material.id),
        );
      }
      const latest = await lessonKitApi.getLessonPackage(lessonPackage.id);
      if (latest.status !== "approved") {
        await lessonKitApi.approveLessonPackage(
          latest.id,
          latest.version ?? 1,
          "Teacher approved complete printable lesson kit",
        );
      }
      setMaterials(approvedMaterials);
      const job = await lessonKitApi.createPrintableLessonKit(
        lessonPackage.id,
        {
          materialIds: approvedMaterials.map((item) => item.id),
          pageSize,
          reviewedConfirmation: true,
        },
      );
      if (job.status !== "completed") {
        setLocalMessage(job.message);
        return;
      }
      const download = await lessonKitApi.getPrintableLessonKitDownload(
        job.exportId,
      );
      window.location.assign(download.downloadUrl);
      onFeedback("Complete lesson kit PDF prepared for printing.");
    } catch (reason) {
      const message =
        reason instanceof Error
          ? reason.message
          : "Printable lesson kit could not be prepared.";
      setLocalMessage(message);
      onFeedback(message);
    } finally {
      setActionBusy(false);
    }
  };

  const needsArtwork = Boolean(
    selected && imageMaterialTypes.includes(selected.type),
  );
  const hasArtwork = Boolean(selected && hasCompleteVisualSet(selected));
  const imageStatus = String(
    selected?.content.imageGenerationStatus ?? "",
  );
  const imageGenerating = ["pending", "processing"].includes(imageStatus);
  const approved = selected?.status === "approved";
  const tokenCount = Number(
    selected?.content.tokens ?? selected?.content.tokenCount ?? 5,
  );
  const goalTitle = lessonPackage.goal;

  return (
    <section>
      <div className="v2-page-heading">
        <h1>Review Printable Content</h1>
        <p>
          Review each finished classroom page, then print the complete kit as one
          PDF.
        </p>
      </div>
      <div className="v2-print-layout">
        <Card className="v2-print-sidebar">
          <div className="v2-print-learner">
            <LearnerAvatar
              learnerId={learner?.id ?? lessonPackage.learnerId}
              avatar={learner?.avatar}
              alt={`${learner?.code ?? "Learner"} avatar`}
              size={64}
            />
            <div>
              <strong>{learner?.code ?? "Learner"}</strong>
              <small>Lesson goal</small>
              <b>{goalTitle}</b>
            </div>
          </div>
          <h3>Printable pages</h3>
          {materials.map((material) => (
            <button
              type="button"
              onClick={() => setSelectedId(material.id)}
              className={`v2-material-nav ${
                selected?.id === material.id ? "is-active" : ""
              }`}
              key={material.id}
            >
              <span>{materialIcon(material.type)}</span>
              <span>{material.title}</span>
              {material.status === "approved" && (
                <b aria-label="Approved">✓</b>
              )}
            </button>
          ))}
        </Card>

        <div className="v2-print-center">
          <Card className="v2-print-preview">
            <div className="v2-preview-head">
              <h2>{title || "Material"} Preview</h2>
              <Button
                variant="secondary"
                disabled={actionBusy}
                onClick={() => void exportPdf()}
              >
                ↓ Print Complete Kit PDF
              </Button>
            </div>
            {needsArtwork && !hasArtwork && (
              <div
                className={`v2-artwork-callout ${
                  imageStatus === "failed" ? "is-failed" : ""
                }`}
                role="status"
              >
                <div>
                  <strong>
                    {imageGenerating
                      ? "Creating classroom images…"
                      : "This page needs classroom images"}
                  </strong>
                  <small>
                    {imageGenerating
                      ? "You can review another page while they finish."
                      : "Create lesson-specific images before approving this page."}
                  </small>
                </div>
                {!imageGenerating && (
                  <Button
                    disabled={imageBusy}
                    onClick={() => void quickEdit("regenerate_artwork")}
                  >
                    {imageBusy ? "Starting…" : "Create images"}
                  </Button>
                )}
              </div>
            )}
            {selected && (
              <div className="v2-paper">
                <PrintableMaterialCanvas
                  material={selected}
                  title={title}
                  instruction={instruction}
                  reward={reward}
                  tokenCount={tokenCount}
                />
              </div>
            )}
          </Card>
          <Card className="v2-print-controls">
            <span>▣ &nbsp; Print view</span>
            <label>
              Page size
              <select
                value={pageSize}
                onChange={(event) => {
                  setPageSize(event.target.value as "Letter" | "A4");
                  setDirty(true);
                }}
              >
                <option>Letter</option>
                <option>A4</option>
              </select>
            </label>
          </Card>
          <Card className="v2-issues">
            <h3>Ready check</h3>
            <div className="v2-print-checks">
              <span>✓ Text is readable</span>
              <span>{hasArtwork || !needsArtwork ? "✓" : "○"} Images ready</span>
              <span>✓ Print-safe layout</span>
            </div>
          </Card>
        </div>

        <Card className="v2-edit-material v2-material-actions">
          <div className="v2-preview-head">
            <h2>Material actions</h2>
            <span
              className={`v2-approval-status ${
                approved ? "is-approved" : ""
              }`}
            >
              {approved ? "✓ Approved" : "Review needed"}
            </span>
          </div>
          <p>
            The finished design is already optimized for low-distraction classroom
            printing.
          </p>
          <button
            type="button"
            className="v2-quick-edit"
            onClick={() => void quickEdit("simplify_wording")}
          >
            T² &nbsp; Make wording shorter
          </button>
          {needsArtwork && (
            <button
              type="button"
              className="v2-quick-edit"
              disabled={imageBusy || imageGenerating}
              onClick={() => void quickEdit("regenerate_artwork")}
            >
              ↻ &nbsp;
              {imageBusy || imageGenerating
                ? "Creating new images…"
                : "Create new images"}
            </button>
          )}
          {selected?.type === "token_board" && (
            <button
              type="button"
              className="v2-quick-edit"
              onClick={() => void quickEdit("adjust_reward")}
            >
              ♢ &nbsp; Suggest another reward
            </button>
          )}
          <details className="v2-optional-edits">
            <summary>Edit text (optional)</summary>
            <label>
              Material title
              <input
                value={title}
                onChange={(event) => {
                  setTitle(event.target.value);
                  setDirty(true);
                }}
              />
            </label>
            <label>
              Instruction
              <textarea
                rows={3}
                value={instruction}
                onChange={(event) => {
                  setInstruction(event.target.value);
                  setDirty(true);
                }}
              />
            </label>
            {selected?.type === "token_board" && (
              <label>
                Reward
                <input
                  value={reward}
                  onChange={(event) => {
                    setReward(event.target.value);
                    setDirty(true);
                  }}
                />
              </label>
            )}
          </details>
          {localMessage && (
            <div className="v2-material-message" role="status">
              {localMessage}
            </div>
          )}
          {dirty && <small role="status">Changes are not saved yet.</small>}
          <Button
            fullWidth
            disabled={!dirty || actionBusy}
            onClick={() =>
              void save()
                .then((value) => {
                  if (value) {
                    setLocalMessage("Changes saved.");
                    onFeedback(`${value.title} changes saved.`);
                  }
                })
                .catch((reason: unknown) => {
                  const message =
                    reason instanceof Error
                      ? reason.message
                      : "Changes could not be saved.";
                  setLocalMessage(message);
                })
            }
          >
            {actionBusy ? "Saving…" : "Save Changes"}
          </Button>
          <Button
            variant="secondary"
            fullWidth
            disabled={actionBusy || approved}
            onClick={() => void approve()}
          >
            {approved
              ? "Approved for Print"
              : imageGenerating
                ? "Check Image Progress"
                : actionBusy
                  ? "Approving…"
                  : "Approve for Print"}
          </Button>
        </Card>
      </div>
      <div className="v2-page-actions">
        <Button variant="secondary" onClick={onBack}>
          Back to Package
        </Button>
      </div>
    </section>
  );
}
