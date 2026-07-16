import { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from "react";
import { lessonKitApi } from "../api/lessonKitApi";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Tag } from "../components/Tag";
import type { LearnerProfile, LearnerRecord } from "../types";

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const ALLOWED_EXTENSIONS = [".txt", ".pdf", ".docx"];
const ALLOWED_FILE_LABEL = "TXT, PDF, or DOCX";
const BUSY_STATES = new Set<LearnerRecord["status"]>([
  "upload_pending",
  "uploaded",
  "validating",
  "parsing",
  "processing",
]);

export function UploadRecordsPage({
  learnerId,
  onContinue,
  onFeedback,
}: {
  learnerId: string;
  onContinue: () => void;
  onFeedback: (message: string) => void;
}) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [learner, setLearner] = useState<LearnerProfile | null>(null);
  const [records, setRecords] = useState<LearnerRecord[]>([]);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [showPaste, setShowPaste] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null);
  const [correction, setCorrection] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const selectedRecord = useMemo(
    () => records.find((record) => record.id === selectedRecordId) ?? null,
    [records, selectedRecordId],
  );
  const hasBusyRecord = records.some((record) => BUSY_STATES.has(record.status));
  const canContinue = records.some((record) => ["ready", "reviewed"].includes(record.status));

  useEffect(() => {
    void Promise.all([
      lessonKitApi.getLearnerById(learnerId),
      lessonKitApi.getRecordsForLearner(learnerId),
    ])
      .then(([profile, items]) => {
        setLearner(profile);
        setRecords(items);
      })
      .catch((error: unknown) => onFeedback(messageFromError(error)));
  }, [learnerId, onFeedback]);

  const replaceRecord = (next: LearnerRecord) => {
    setRecords((current) => {
      const exists = current.some((record) => record.id === next.id);
      return exists
        ? current.map((record) => (record.id === next.id ? next : record))
        : [next, ...current];
    });
  };

  const uploadFile = async (file: File) => {
    const validationMessage = validateSelectedFile(file);
    if (validationMessage) {
      onFeedback(validationMessage);
      return;
    }
    if (records.some((record) => record.fileName === file.name && record.status !== "failed")) {
      onFeedback(`${file.name} is already in the upload list.`);
      return;
    }
    try {
      const intent = await lessonKitApi.requestRecordUpload(learnerId, file);
      replaceRecord(intent.record);
      setUploadProgress((current) => ({ ...current, [intent.record.id]: 0 }));
      await lessonKitApi.uploadRecordObject(intent, file, (percent) =>
        setUploadProgress((current) => ({ ...current, [intent.record.id]: percent })),
      );
      const completed = await lessonKitApi.completeRecordUpload(learnerId, intent.record.id);
      replaceRecord(completed);
      setSelectedRecordId(completed.id);
      setCorrection(completed.effectiveText || completed.extractedText || "");
      onFeedback(statusMessage(completed));
    } catch (error: unknown) {
      onFeedback(messageFromError(error));
    }
  };

  const handleFileSelection = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    for (const file of files) await uploadFile(file);
  };

  const handleDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setIsDragging(false);
    const files = Array.from(event.dataTransfer.files);
    void files.reduce(
      (chain, file) => chain.then(() => uploadFile(file)),
      Promise.resolve(),
    );
  };

  const savePaste = async () => {
    if (!pasteText.trim()) return;
    setIsSaving(true);
    try {
      const record = await lessonKitApi.addRecordForLearner(learnerId, {
        fileName: "Teacher pasted notes.txt",
        fileType: "TXT",
        text: pasteText.trim(),
      });
      replaceRecord(record);
      setPasteText("");
      setShowPaste(false);
      onFeedback("Teacher-entered text saved for profile review.");
    } catch (error: unknown) {
      onFeedback(messageFromError(error));
    } finally {
      setIsSaving(false);
    }
  };

  const openReview = (record: LearnerRecord) => {
    setSelectedRecordId(record.id);
    setCorrection(record.effectiveText || record.teacherCorrectedText || record.extractedText || "");
  };

  const saveCorrection = async () => {
    if (!selectedRecord || !correction.trim()) return;
    setIsSaving(true);
    try {
      const updated = await lessonKitApi.correctRecordText(
        learnerId,
        selectedRecord.id,
        correction.trim(),
        selectedRecord.version,
      );
      replaceRecord(updated);
      setCorrection(updated.effectiveText || correction.trim());
      onFeedback("Teacher correction saved.");
    } catch (error: unknown) {
      onFeedback(messageFromError(error));
    } finally {
      setIsSaving(false);
    }
  };

  const deleteRecord = async (record: LearnerRecord) => {
    if (!window.confirm(`Delete ${record.fileName} and its extracted text?`)) return;
    try {
      const result = await lessonKitApi.deleteLearnerRecord(learnerId, record.id);
      if (result.status === "deleted") {
        setRecords((current) => current.filter((item) => item.id !== record.id));
        if (selectedRecordId === record.id) setSelectedRecordId(null);
      } else {
        replaceRecord({ ...record, deletionStatus: "failed" });
      }
      onFeedback(result.message);
    } catch (error: unknown) {
      onFeedback(messageFromError(error));
    }
  };

  return (
    <section>
      <div className="v2-page-heading">
        <h1>Upload Learner Records</h1>
        <p>Upload notes, assessments, or session documents for {learner?.code ?? "the learner"}.</p>
      </div>

      <div className="v2-upload-layout">
        <Card className="v2-upload-main">
          <div className="v2-upload-learner">
            <span>{learner?.avatar ?? "🧒🏻"}</span>
            <div>
              <h2>{learner?.code ?? "Learner N-501"} <small>· Age {learner?.age ?? 7}</small></h2>
              <div>{learner?.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div>
            </div>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            className="v2-visually-hidden"
            accept={ALLOWED_EXTENSIONS.join(",")}
            multiple
            onChange={handleFileSelection}
          />
          <button
            className={`v2-dropzone ${isDragging ? "is-dragging" : ""}`}
            type="button"
            onClick={() => fileInputRef.current?.click()}
            onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
          >
            <span>☁</span>
            <h2>Drag and drop files here</h2>
            <p>{ALLOWED_FILE_LABEL} · up to 10 MB</p>
          </button>

          <div className="v2-upload-security-note">
            Records are private and validated before parsing. Malware scanning is not configured for this demo.
          </div>

          <div className="v2-or"><span />or<span /></div>
          <button className="v2-paste-link" type="button" onClick={() => setShowPaste((value) => !value)}>
            ▣ &nbsp; Paste text instead
          </button>
          {showPaste && (
            <div className="v2-paste-editor">
              <textarea
                autoFocus
                className="v2-paste-area"
                value={pasteText}
                placeholder="Paste learner notes here…"
                onChange={(event) => setPasteText(event.target.value)}
              />
              <Button variant="secondary" disabled={!pasteText.trim() || isSaving} onClick={() => void savePaste()}>
                Save pasted text
              </Button>
            </div>
          )}

          <h3>Recent uploads</h3>
          <div className="v2-upload-list">
            {records.map((record) => {
              const status = presentStatus(record);
              return (
                <div key={record.id} className={selectedRecordId === record.id ? "is-selected" : ""}>
                  <span className={`v2-file-icon v2-file-${record.fileType.toLowerCase()}`}>{record.fileType}</span>
                  <button className="v2-record-name" type="button" onClick={() => openReview(record)}>
                    <strong>{record.fileName}</strong>
                    {uploadProgress[record.id] !== undefined && BUSY_STATES.has(record.status) && (
                      <span className="v2-upload-progress"><i style={{ width: `${uploadProgress[record.id]}%` }} /></span>
                    )}
                  </button>
                  <Tag tone={status.tone}>{status.label}</Tag>
                  <small>{record.parsingMessage || record.uploadedAt}</small>
                  <button type="button" onClick={() => void deleteRecord(record)} aria-label={`Delete ${record.fileName}`}>×</button>
                </div>
              );
            })}
          </div>

          {selectedRecord && (
            <div className={`v2-record-review v2-record-review--${selectedRecord.status}`}>
              <div>
                <h3>Extracted text review</h3>
                <Tag tone={presentStatus(selectedRecord).tone}>{presentStatus(selectedRecord).label}</Tag>
              </div>
              {selectedRecord.status === "needs_ocr" && (
                <p>This PDF appears scanned or image-only. OCR is not configured; paste or correct the text below.</p>
              )}
              {selectedRecord.status === "failed" && <p>Parsing failed. You can delete the record and try again, or paste the text manually.</p>}
              <textarea value={correction} onChange={(event) => setCorrection(event.target.value)} placeholder="Enter corrected learner record text…" />
              <Button variant="secondary" disabled={!correction.trim() || isSaving} onClick={() => void saveCorrection()}>
                Save correction
              </Button>
            </div>
          )}

          <div className="v2-upload-actions">
            <Button variant="secondary" onClick={() => fileInputRef.current?.click()}>＋ Add another file</Button>
            <Button disabled={!canContinue || hasBusyRecord} onClick={onContinue}>Continue</Button>
          </div>
        </Card>

        <Card className="v2-next-panel">
          <h2>What happens next</h2>
          <ol>
            <li><b>1</b><span>▤</span><strong>Text is extracted<br />from each record</strong></li>
            <li><b>2</b><span>♙</span><strong>You review and edit<br />learner information</strong></li>
            <li><b>3</b><span>◎</span><strong>You define the<br />lesson goal</strong></li>
          </ol>
          <div className="v2-upload-complete">✓ &nbsp; {records.filter((record) => record.status !== "deleted").length} records on file</div>
        </Card>
      </div>
    </section>
  );
}

function validateSelectedFile(file: File): string | null {
  const lowerName = file.name.toLowerCase();
  const extension = `.${lowerName.split(".").pop() ?? ""}`;
  if (!ALLOWED_EXTENSIONS.includes(extension)) return `Unsupported file type. Please use ${ALLOWED_FILE_LABEL}.`;
  if (/\.(exe|js|html|svg|bat|sh|php|zip|rar|7z|tar|gz|docm|xlsm|pptm)$/i.test(lowerName)) return "This file type is not allowed for learner records.";
  if (file.size > MAX_UPLOAD_BYTES) return "File is too large. Maximum upload size is 10 MB.";
  if (file.size === 0) return "Empty files cannot be uploaded.";
  return null;
}

function presentStatus(record: LearnerRecord): { label: string; tone: "blue" | "green" | "purple" | "amber" | "gray" } {
  if (record.deletionStatus === "failed") return { label: "Delete failed", tone: "amber" };
  const statuses: Record<LearnerRecord["status"], { label: string; tone: "blue" | "green" | "purple" | "amber" | "gray" }> = {
    upload_pending: { label: "Uploading", tone: "blue" }, uploaded: { label: "Uploaded", tone: "blue" },
    validating: { label: "Validating", tone: "blue" }, parsing: { label: "Parsing", tone: "purple" },
    processing: { label: "Processing", tone: "purple" }, needs_ocr: { label: "Needs OCR", tone: "amber" },
    needs_review: { label: "Review text", tone: "amber" }, ready: { label: "Ready", tone: "green" },
    reviewed: { label: "Reviewed", tone: "green" }, failed: { label: "Failed", tone: "amber" },
    deleted: { label: "Deleted", tone: "gray" },
  };
  return statuses[record.status];
}

function statusMessage(record: LearnerRecord): string {
  if (record.status === "needs_ocr") return `${record.fileName} needs OCR or teacher-entered text.`;
  if (record.status === "failed") return `${record.fileName} could not be parsed.`;
  return `${record.fileName} is ready for extracted-text review.`;
}

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "The record operation could not be completed.";
}
