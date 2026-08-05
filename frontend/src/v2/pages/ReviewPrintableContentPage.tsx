import { useCallback, useEffect, useRef, useState } from "react";
import { lessonKitApi } from "../api/lessonKitApi";
import { resolveBackendAssetUrl } from "../api/backendClient";
import { LearnerAvatar } from "../components/Avatar";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { PrintableMaterialCanvas } from "../components/PrintableMaterialCanvas";
import {
  executePdfArtifactDownload,
  initialPdfDownloadState,
} from "../pdfDownload";
import type {
  GeneratedMaterial,
  LearnerProfile,
  LessonPackage,
  MaterialQuickEditAction,
  PdfDownloadState,
  PackagePrintReadiness,
  PackagePrintReadinessBlocker,
  PrintPreset,
  PrintPresetCatalog,
  PrintTextProfile,
  ScenarioCardItem,
} from "../types";
import { PrintReadinessPanel } from "../components/PrintReadinessPanel";
import { nextPendingMaterialId } from "../printReadinessModel";
import { PrintPresetPicker } from "../components/PrintPresetPicker";
import { printPresetLabels,readSelectedPageSize,readSelectedPrintPreset,readSelectedTextProfile,rememberPrintableArtifact,rememberSelectedPageSize,rememberSelectedPrintPreset,rememberSelectedTextProfile } from "../printPresetModel";

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
  "blue_line_activity",
  "visual_timer",
];

function hasCompleteVisualSet(material: GeneratedMaterial): boolean {
  if (material.visualAssetPlan) {
    return material.visualAssetPlan.visualItems.every((item) =>
      !item.required ||
      ["ready", "needs_review"].includes(item.status) ||
      Boolean(item.fallbackAssetId),
    );
  }
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

function isCurrentRevisionApproved(material: GeneratedMaterial): boolean {
  if (material.status !== "approved") return false;
  if (!material.materialSpec) return true;
  return (
    material.materialSpec.approval.status === "approved" &&
    material.materialSpec.approval.approvedRevision === material.materialSpec.revision
  );
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
  const [pageSize, setPageSize] = useState<"Letter" | "A4">(() => lessonPackage ? readSelectedPageSize(lessonPackage.id) : "Letter");
  const [textProfile, setTextProfile] = useState<PrintTextProfile>(() => lessonPackage ? readSelectedTextProfile(lessonPackage.id) : "standard");
  const [dirty, setDirty] = useState(false);
  const [imageBusy, setImageBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [visualBusyId, setVisualBusyId] = useState("");
  const [replacementAssetIds, setReplacementAssetIds] = useState<Record<string,string>>({});
  const [semanticDraft, setSemanticDraft] = useState<Record<string,unknown>>({});
  const [localMessage, setLocalMessage] = useState("");
  const [pdfDownload, setPdfDownload] = useState<PdfDownloadState>(
    initialPdfDownloadState,
  );
  const [printReadiness, setPrintReadiness] = useState<PackagePrintReadiness | null>(null);
  const [printPresetCatalog, setPrintPresetCatalog] = useState<PrintPresetCatalog | null>(null);
  const [printPreset, setPrintPreset] = useState<PrintPreset>(() => lessonPackage ? readSelectedPrintPreset(lessonPackage.id) : "complete_kit");
  const reviewRequests = useRef(new Set<string>());
  const packageApprovalAttempts = useRef(new Set<string>());
  const refreshPrintReadiness = useCallback(async () => {
    if (!lessonPackage) return null;
    const value = await lessonKitApi.getPackagePrintReadiness(lessonPackage.id);
    setPrintReadiness(value);
    return value;
  }, [lessonPackage?.id]);

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
        void refreshPrintReadiness();
      })
      .catch((reason: unknown) => {
        const message =
          reason instanceof Error
            ? reason.message
            : "Printable materials could not be loaded.";
        setLocalMessage(message);
      });
  }, [lessonPackage?.id, initialSelectedId, refreshPrintReadiness]);

  useEffect(() => {
    if (!lessonPackage) return;
    let active = true;
    setPrintPreset(readSelectedPrintPreset(lessonPackage.id));
    setPageSize(readSelectedPageSize(lessonPackage.id));
    setTextProfile(readSelectedTextProfile(lessonPackage.id));
    setPrintPresetCatalog(null);
    void lessonKitApi.getPrintPresetCatalog(lessonPackage.id, pageSize, textProfile)
      .then((value) => { if (active) setPrintPresetCatalog(value); })
      .catch((reason: unknown) => { if (active) setLocalMessage(reason instanceof Error ? reason.message : "Print choices could not be loaded."); });
    return () => { active = false; };
  }, [lessonPackage?.id, lessonPackage?.version, pageSize, textProfile]);

  const selected =
    materials.find((item) => item.id === selectedId) ?? materials[0];

  useEffect(() => {
    if (!selected?.materialSpec || selected.materialSchemaVersion !== 1) return;
    const spec = selected.materialSpec;
    const key = `${selected.id}:${spec.revision}`;
    if (
      spec.semanticValidation.status !== "passed" ||
      spec.safetyValidation.status !== "passed" ||
      spec.approval.reviewedRevision === spec.revision ||
      reviewRequests.current.has(key)
    ) return;
    reviewRequests.current.add(key);
    void lessonKitApi.reviewGeneratedMaterial(selected.id)
      .then((value) => {setMaterials((current) => current.map((item) => item.id === value.id ? value : item));void refreshPrintReadiness();})
      .catch((reason: unknown) => setLocalMessage(reason instanceof Error ? reason.message : "This revision could not be marked reviewed."));
  }, [selected?.id, selected?.materialSpec?.revision,refreshPrintReadiness]);
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
        if (!cancelled) {setMaterials(items);void refreshPrintReadiness();}
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
  }, [lessonPackage?.id, imageStateKey,refreshPrintReadiness]);

  const approvalStateKey = materials
    .map((item) => `${item.id}:${item.status}:${item.materialSpec?.revision ?? item.version}:${item.materialSpec?.approval.approvedRevision ?? 0}`)
    .join("|");
  useEffect(() => {
    if (!lessonPackage || materials.length === 0 || !materials.every(isCurrentRevisionApproved)) return;
    const attemptKey = `${lessonPackage.id}:${approvalStateKey}`;
    if (packageApprovalAttempts.current.has(attemptKey)) return;
    packageApprovalAttempts.current.add(attemptKey);
    let cancelled = false;
    void (async () => {
      try {
        const latest = await lessonKitApi.getLessonPackage(lessonPackage.id);
        const approved = latest.status === "approved"
          ? latest
          : await lessonKitApi.approveLessonPackage(
              latest.id,
              latest.version ?? 1,
              "Teacher approved every current printable material revision",
            );
        if (cancelled) return;
        setMaterials(approved.materials);
        const readiness = await refreshPrintReadiness();
        if (cancelled) return;
        if (readiness?.ready) {
          setLocalMessage("All pages are approved. PDF download is ready.");
          onFeedback("All pages approved. PDF download is now available.");
        } else {
          setLocalMessage("Your approvals are saved. Finishing the PDF readiness check…");
        }
      } catch (reason) {
        if (!cancelled) {
          setLocalMessage(reason instanceof Error ? reason.message : "The approved package could not be finalized.");
        }
      }
    })();
    return () => { cancelled = true; };
  }, [lessonPackage?.id, approvalStateKey, refreshPrintReadiness, onFeedback]);

  useEffect(() => {
    if (!selected) return;
    setTitle(selected.title);
    setInstruction(String(selected.content.instruction ?? ""));
    setReward(
      String(selected.content.reward ?? "Teacher-confirmed reward"),
    );
    setPageSize(selected.printLayout.pageSize);
    setSemanticDraft(selected.materialSpec ? {...selected.materialSpec.content} : {});
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
        ...semanticDraft,
        instruction,
        ...(selected.type === "token_board" ? { reward, earnedReward: reward } : {}),
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

  const approve = async (openNext = false) => {
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
      const reviewed = saved.materialSpec && saved.materialSpec.approval.reviewedRevision !== saved.materialSpec.revision
        ? await lessonKitApi.reviewGeneratedMaterial(saved.id)
        : saved;
      const value = await lessonKitApi.approveGeneratedMaterial(reviewed.id);
      replaceMaterial(value);
      const readiness = await refreshPrintReadiness();
      if (openNext) {
        const nextId = nextPendingMaterialId(readiness, value.id);
        if (nextId) setSelectedId(nextId);
      }
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
      await refreshPrintReadiness();
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

  const updateVisual = async (
    visualId: string,
    action: "regenerate" | "fallback" | "approve" | "reject" | "replace",
  ) => {
    if (!selected || visualBusyId) return;
    setVisualBusyId(visualId);
    setLocalMessage("");
    try {
      const value = action === "regenerate"
        ? await lessonKitApi.regenerateMaterialVisual(selected.id, visualId)
        : action === "fallback"
          ? await lessonKitApi.useMaterialVisualFallback(selected.id, visualId)
          : action === "replace"
            ? await lessonKitApi.replaceMaterialVisual(selected.id, visualId, replacementAssetIds[visualId] ?? "")
            : await lessonKitApi.reviewMaterialVisual(selected.id, visualId, action);
      replaceMaterial(value);
      await refreshPrintReadiness();
      setLocalMessage(`Visual ${action} completed.`);
    } catch (reason) {
      setLocalMessage(reason instanceof Error ? reason.message : "The visual could not be updated.");
    } finally {
      setVisualBusyId("");
    }
  };

  const regenerateSelectedMaterial = async () => {
    if (!selected || actionBusy) return;
    setActionBusy(true);
    setLocalMessage("");
    try {
      const value = await lessonKitApi.regenerateNextSessionMaterial(
        lessonPackage.id,
        selected.id,
        selected.version ?? 1,
      );
      replaceMaterial(value);
      await refreshPrintReadiness();
      setLocalMessage("Only this material was regenerated. Its approval now requires review.");
    } catch (reason) {
      setLocalMessage(reason instanceof Error ? reason.message : "This material could not be regenerated.");
    } finally {
      setActionBusy(false);
    }
  };

  const regenerateScenario = async (
    scenarioId: string,
    teacherInstruction: string,
  ) => {
    if (!selected || actionBusy) return;
    setActionBusy(true);
    setLocalMessage("");
    try {
      const value = await lessonKitApi.regenerateNextSessionScenario(
        lessonPackage.id,
        selected.id,
        scenarioId,
        teacherInstruction,
        selected.version ?? 1,
      );
      replaceMaterial(value);
      await refreshPrintReadiness();
      setLocalMessage("Only the selected scenario revision changed; unrelated visuals were retained.");
    } catch (reason) {
      setLocalMessage(reason instanceof Error ? reason.message : "This scenario could not be regenerated.");
    } finally {
      setActionBusy(false);
    }
  };

  const exportPdf = async () => {
    setActionBusy(true);
    setLocalMessage("");
    try {
      const readiness = await refreshPrintReadiness();
      if (!readiness?.ready) {
        const next = readiness?.recommendedNextAction;
        if (next?.materialId) setSelectedId(next.materialId);
        setLocalMessage(next?.explanation ?? "Printing is blocked until readiness checks finish.");
        return;
      }
      const artifact = await executePdfArtifactDownload({
        prepareArtifact: () =>
          lessonKitApi.createPrintableLessonKitArtifact(lessonPackage.id, {
          materialIds: [],
          printPreset,
          pageSize,
          textProfile,
          reviewedConfirmation: true,
          }),
        onState: (state) => {
          setPdfDownload(state);
          setLocalMessage(state.message);
        },
      });
      rememberPrintableArtifact(artifact);
      onFeedback(`${printPresetLabels[printPreset]} PDF download started.`);
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

  const fixReadiness = async (item: PackagePrintReadinessBlocker) => {
    if (item.materialId) {
      setSelectedId(item.materialId);
      setLocalMessage(item.explanation);
      return;
    }
    if (item.recoveryAction === "approve_package") {
      setActionBusy(true);
      try {
        const latest = await lessonKitApi.getLessonPackage(lessonPackage.id);
        await lessonKitApi.approveLessonPackage(latest.id, latest.version ?? 1, "Teacher explicitly approved the complete printable lesson kit");
        await refreshPrintReadiness();
        setLocalMessage("Complete package approved. Download is now available.");
      } catch (reason) {
        setLocalMessage(reason instanceof Error ? reason.message : "The package could not be approved.");
      } finally {
        setActionBusy(false);
      }
      return;
    }
    if (["revalidate_package", "repair_package"].includes(item.recoveryAction)) {
      setActionBusy(true);
      try {
        const updated = await lessonKitApi.revalidateLessonPackage(lessonPackage.id);
        setMaterials(updated.materials);
        const readiness = await refreshPrintReadiness();
        setLocalMessage(
          readiness?.ready
            ? "The complete package is ready to download."
            : readiness?.recommendedNextAction?.explanation ?? "Package checks refreshed.",
        );
      } catch (reason) {
        setLocalMessage(reason instanceof Error ? reason.message : "Package checks could not be refreshed.");
      } finally {
        setActionBusy(false);
      }
      return;
    }
    setLocalMessage(item.explanation);
    onBack();
  };

  const needsArtwork = Boolean(
    selected && imageMaterialTypes.includes(selected.type),
  );
  const hasArtwork = Boolean(selected && hasCompleteVisualSet(selected));
  const imageStatus = String(
    selected?.content.imageGenerationStatus ?? "",
  );
  const imageGenerating = ["pending", "processing"].includes(imageStatus);
  const rendererVisuals = Array.isArray(selected?.content.visualItems)
    ? selected.content.visualItems.filter((item): item is Record<string,unknown> => Boolean(item) && typeof item === "object")
    : [];
  const setSemantic = (key:string,value:unknown) => {
    setSemanticDraft((current)=>({...current,[key]:value}));
    setDirty(true);
  };
  const personalizedFactors = learner?.normalizedProfile?.factors.filter((factor)=>
    selected?.materialSpec?.profileFactorIds.includes(factor.id),
  ) ?? [];
  const accessConstraints = selected?.materialSpec ? [
    ...selected.materialSpec.designConstraints.layoutRequirements,
    ...selected.materialSpec.designConstraints.motorAccessRequirements,
    ...selected.materialSpec.designConstraints.prohibitedAudioFeatures,
  ] : [];
  const semanticExclusions = selected?.materialSpec
    ? [
        ...("prohibitedImagery" in selected.materialSpec.content ? selected.materialSpec.content.prohibitedImagery : []),
        ...("prohibitedRewardSubstitutions" in selected.materialSpec.content ? selected.materialSpec.content.prohibitedRewardSubstitutions : []),
        ...selected.materialSpec.designConstraints.prohibitedVisualFeatures,
      ]
    : [];
  const approved = selected?.status === "approved";
  const tokenCount = Number(
    selected?.content.tokens ?? selected?.content.tokenCount ?? 5,
  );
  const goalTitle = lessonPackage.goal;
  const selectedScenarios = selected?.type === "scenario_cards"
    ? ((selected.materialSpec?.content as { scenarios?: ScenarioCardItem[] } | undefined)?.scenarios ?? [])
    : [];

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
                className="v2-preview-download-button"
                disabled={actionBusy || !printReadiness?.ready || !printPresetCatalog?.presets.find((item) => item.printPreset === printPreset)?.available}
                onClick={() => void exportPdf()}
              >
                {pdfDownload.phase === "preparing"
                  ? "Preparing PDF…"
                  : pdfDownload.phase === "download_starting"
                    ? "Download starting…"
                    : pdfDownload.phase === "failed"
                      ? `Retry ${printPresetLabels[printPreset]} PDF`
                      : `↓ Download ${printPresetLabels[printPreset]} PDF`}
              </Button>
            </div>
            <PrintReadinessPanel readiness={printReadiness} busy={actionBusy} onFix={(item)=>void fixReadiness(item)}/>
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
            {selected?.visualAssetPlan && selected.visualAssetPlan.visualItems.length > 0 && (
              <section className="v2-visual-review" aria-label="Instructional visual review">
                <div className="v2-visual-review-heading">
                  <div><h3>Instructional visuals</h3><p>Review each image against the text or task it represents.</p></div>
                  <small>{selected.visualAssetPlan.visualItems.length} planned · {selected.visualAssetPlan.minimumRequiredVisuals} required</small>
                </div>
                <div className="v2-visual-review-grid">
                  {selected.visualAssetPlan.visualItems.map((visual) => {
                    const rendered = rendererVisuals.find((item) => item.id === visual.id);
                    const source = resolveBackendAssetUrl(rendered?.imageUrl)
                      ?? (typeof rendered?.imageBase64 === "string" ? `data:image/png;base64,${rendered.imageBase64}` : null);
                    const usingFallback = visual.assetId === visual.fallbackAssetId || visual.status === "failed" || (!visual.assetId && Boolean(visual.fallbackAssetId));
                    return <article key={visual.id} className={visual.reviewStatus === "rejected" ? "is-rejected" : ""}>
                      <div className="v2-visual-review-image">{source
                        ? <img src={source} alt={visual.altText} />
                        : <span role="status">Visual unavailable</span>}</div>
                      <div className="v2-visual-review-copy">
                        <span>{visual.role.replace(/_/g," ")}{visual.required ? " · required" : " · optional"}</span>
                        <strong>{visual.visibleLabel}</strong>
                        <p>{visual.instructionalPurpose}</p>
                        <small>{usingFallback ? "Deterministic fallback visible" : `${visual.generationMethod.replace(/_/g," ")} · ${visual.status.replace(/_/g," ")}`} · review: {visual.reviewStatus}</small>
                      </div>
                      <div className="v2-visual-review-actions">
                        {visual.generationMethod === "ai_generated" && <button type="button" disabled={Boolean(visualBusyId)} onClick={() => void updateVisual(visual.id,"regenerate")}>Regenerate this image</button>}
                        {visual.fallbackAssetId && <button type="button" disabled={Boolean(visualBusyId)} onClick={() => void updateVisual(visual.id,"fallback")}>Use fallback</button>}
                        <button type="button" disabled={Boolean(visualBusyId)} onClick={() => void updateVisual(visual.id,"approve")}>Approve visual</button>
                        <button type="button" disabled={Boolean(visualBusyId)} onClick={() => void updateVisual(visual.id,"reject")}>Reject visual</button>
                        <details><summary>Replace from asset library</summary><input aria-label={`Replacement asset ID for ${visual.visibleLabel}`} placeholder="Approved asset ID" value={replacementAssetIds[visual.id] ?? ""} onChange={(event)=>setReplacementAssetIds((current)=>({...current,[visual.id]:event.target.value}))}/><button type="button" disabled={Boolean(visualBusyId) || !(replacementAssetIds[visual.id] ?? "").trim()} onClick={() => void updateVisual(visual.id,"replace")}>Replace this image</button></details>
                      </div>
                    </article>;
                  })}
                </div>
              </section>
            )}
          </Card>
          {selected?.materialSpec && <details className="v2-personalization-trace"><summary><span><b>Why this material is personalized</b><small>Profile needs and your confirmed choices</small></span><em>View</em></summary><div><section><h4>Learner needs applied</h4>{personalizedFactors.length?<ul>{personalizedFactors.slice(0,4).map((factor)=><li key={factor.id}><b>{factor.label}:</b> {factor.value}</li>)}</ul>:<p>Uses the current teacher-reviewed learner profile.</p>}</section><section><h4>Your choices applied</h4><p>Uses your confirmed goal, classroom situations, and material selections.</p></section>{accessConstraints.length>0&&<section><h4>Access supports</h4><ul>{accessConstraints.slice(0,4).map((value)=><li key={value}>{value}</li>)}</ul></section>}{semanticExclusions.length>0&&<section><h4>Kept out</h4><ul>{semanticExclusions.slice(0,4).map((value)=><li key={value}>{value}</li>)}</ul></section>}</div></details>}
          <Card className="v2-print-controls">
            <span>▣ &nbsp; Print view</span>
            <PrintPresetPicker compact catalog={printPresetCatalog} selected={printPreset} onSelect={(value) => { setPrintPreset(value); rememberSelectedPrintPreset(lessonPackage.id, value); setPdfDownload(initialPdfDownloadState); }}/>
            <label>
              Page size
              <select
                value={pageSize}
                onChange={(event) => {
                  const value = event.target.value as "Letter" | "A4";
                  setPageSize(value);
                  rememberSelectedPageSize(lessonPackage.id, value);
                  setDirty(true);
                }}
              >
                <option>Letter</option>
                <option>A4</option>
              </select>
            </label>
            <label>
              Text size
              <select
                value={textProfile}
                onChange={(event) => {
                  const value = event.target.value as PrintTextProfile;
                  setTextProfile(value);
                  rememberSelectedTextProfile(lessonPackage.id, value);
                  setDirty(true);
                }}
              >
                <option value="standard">Standard</option>
                <option value="large">Large Print</option>
              </select>
            </label>
            <p className="v2-print-profile-note">Large Print may use extra pages so teacher text and learner labels remain readable.</p>
          </Card>
          <Card className="v2-issues">
            <h3>Ready check</h3>
            <div className="v2-print-checks">
              <span>{selected?.materialSpec?.semanticValidation.status === "failed" ? "!" : "✓"} Semantic content validated</span>
              <span>{hasArtwork || !needsArtwork ? "✓" : "○"} Images ready</span>
              <span>{selected?.materialSpec?.safetyValidation.status === "failed" ? "!" : "✓"} Safety revalidated</span>
            </div>
            {selected?.materialSpec?.safetyValidation.issues.map((issue) => <article key={issue.id} className="v2-safety-issue">
              <strong>{issue.severity === "blocking" ? "Blocking" : "Warning"}: {issue.category.replace(/_/g, " ")}</strong>
              <p>{issue.message}</p>
              <small>Affected material: {selected.title} · related constraints: {issue.profileFactorIds.join(", ") || "none recorded"}</small>
              <em>Suggested correction: {issue.suggestedCorrection}</em>
              <small>Revalidation: {selected.materialSpec?.safetyValidation.status}</small>
            </article>)}
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
            disabled={!selected || actionBusy}
            onClick={() => void regenerateSelectedMaterial()}
          >
            ↻ &nbsp; Regenerate this material only
          </button>
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
                : "Generate all pending visuals"}
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
          {selectedScenarios.length > 0 && (
              <details className="v2-optional-edits">
                <summary>Regenerate one scenario only</summary>
                {selectedScenarios.map((scenario) => (
                  <button
                    key={scenario.id}
                    type="button"
                    className="v2-quick-edit"
                    disabled={actionBusy}
                    onClick={() => void regenerateScenario(
                      scenario.id,
                      scenario.teacherWording,
                    )}
                  >
                    Regenerate {scenario.context}
                  </button>
                ))}
              </details>
            )}
          <details className="v2-optional-edits">
            <summary>Edit semantic material fields</summary>
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
              <><label>Exact token count<input type="number" min={1} max={10} value={Number(semanticDraft.exactTokenCount ?? 5)} onChange={(event)=>setSemantic("exactTokenCount",Number(event.target.value))}/></label><label>Token symbol or theme<input value={String(semanticDraft.tokenSymbolOrTheme ?? "")} onChange={(event)=>setSemantic("tokenSymbolOrTheme",event.target.value)}/></label><label>Reward<input value={reward} onChange={(event) => {setReward(event.target.value);setSemantic("earnedReward",event.target.value);}}/></label><label>Specific praise<input value={String(semanticDraft.specificPraise ?? "")} onChange={(event)=>setSemantic("specificPraise",event.target.value)}/></label></>
            )}
            {(selected?.type === "help_card" || selected?.type === "break_card") && <><label>Communication phrase<input value={String(semanticDraft.exactCommunicationPhrase ?? "")} onChange={(event)=>setSemantic("exactCommunicationPhrase",event.target.value)}/></label><label>Teacher action<textarea rows={3} value={String(semanticDraft.teacherResponseAfterUse ?? "")} onChange={(event)=>setSemantic("teacherResponseAfterUse",event.target.value)}/></label></>}
            {selected?.type === "first_then_board" && <><label>FIRST task<input value={String(semanticDraft.firstTask ?? "")} onChange={(event)=>setSemantic("firstTask",event.target.value)}/></label><label>THEN reward<input value={String(semanticDraft.thenOutcome ?? "")} onChange={(event)=>setSemantic("thenOutcome",event.target.value)}/></label><label>Completion criterion<textarea rows={2} value={String(semanticDraft.completionCriterion ?? "")} onChange={(event)=>setSemantic("completionCriterion",event.target.value)}/></label><label>Return support<textarea rows={2} value={String(semanticDraft.returnOrTransitionInstruction ?? "")} onChange={(event)=>setSemantic("returnOrTransitionInstruction",event.target.value)}/></label></>}
            {selected?.type === "blue_line_activity" && <><label>Station labels<textarea rows={3} value={Array.isArray(semanticDraft.answerKeyOrExpectedSequence)?semanticDraft.answerKeyOrExpectedSequence.join("\n"):""} onChange={(event)=>setSemantic("answerKeyOrExpectedSequence",event.target.value.split("\n").map((value)=>value.trim()).filter(Boolean))}/></label><label>Learner action<textarea rows={3} value={String(semanticDraft.learnerAction ?? "")} onChange={(event)=>setSemantic("learnerAction",event.target.value)}/></label></>}
            {selected?.type === "scenario_cards" && Array.isArray(semanticDraft.scenarios) && <fieldset><legend>Scenario teacher wording</legend>{semanticDraft.scenarios.map((scenario,index)=>{const value=scenario as Record<string,unknown>;return <label key={String(value.id ?? index)}>{String(value.context ?? `Scenario ${index+1}`)}<textarea rows={2} value={String(value.teacherWording ?? "")} onChange={(event)=>setSemantic("scenarios",(semanticDraft.scenarios as Record<string,unknown>[]).map((item,itemIndex)=>itemIndex===index?{...item,teacherWording:event.target.value}:item))}/></label>;})}</fieldset>}
            {selected?.type === "data_sheet" && <label>Data-sheet fields<textarea rows={5} value={Array.isArray(semanticDraft.exactColumns)?semanticDraft.exactColumns.join("\n"):""} onChange={(event)=>setSemantic("exactColumns",event.target.value.split("\n").map((value)=>value.trim()).filter(Boolean))}/></label>}
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
            onClick={() => void approve(false)}
          >
            {approved
              ? "Approved for Print"
              : imageGenerating
                ? "Check Image Progress"
                : actionBusy
                  ? "Approving…"
                  : "Approve for Print"}
          </Button>
          {!approved && <Button variant="secondary" fullWidth disabled={actionBusy} onClick={() => void approve(true)}>Approve and open next pending item</Button>}
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
