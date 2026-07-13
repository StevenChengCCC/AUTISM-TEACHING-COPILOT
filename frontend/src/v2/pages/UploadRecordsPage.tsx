import { ChangeEvent, useEffect, useRef, useState } from "react";
import { lessonKitApi } from "../api/lessonKitApi";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Tag } from "../components/Tag";
import type { LearnerProfile, LearnerRecord } from "../types";

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const ALLOWED_EXTENSIONS = [".txt", ".pdf", ".docx", ".png", ".jpg", ".jpeg"];
const ALLOWED_FILE_LABEL = "TXT, PDF, DOCX, PNG, JPG";

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
  const [showPaste, setShowPaste] = useState(false);

  useEffect(() => {
    void Promise.all([
      lessonKitApi.getLearnerById(learnerId),
      lessonKitApi.getRecordsForLearner(learnerId),
    ]).then(([profile, items]) => {
      setLearner(profile);
      setRecords(items);
    });
  }, [learnerId]);

  const addMockFile = async (
    name = "Supplemental classroom notes.txt",
    text = "Classroom observation ready for teacher review.",
  ) => {
    if (records.some((record) => record.fileName === name)) {
      onFeedback(`${name} is already in the upload list.`);
      return;
    }
    const record = await lessonKitApi.addRecordForLearner(learnerId, {
      fileName: name,
      fileType: fileTypeFromName(name),
      text,
    });
    setRecords((current) => [...current, record]);
    onFeedback(`${name} added.`);
  };

  const handleFileSelection = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const validationMessage = validateSelectedFile(file);
    if (validationMessage) {
      onFeedback(validationMessage);
      return;
    }
    await addMockFile(
      file.name,
      "File metadata accepted for demo review. Real parsing and malware scanning will run in the backend upload pipeline later.",
    );
  };

  return (
    <section>
      <div className="v2-page-heading">
        <h1>Upload Learner Records</h1>
        <p>
          Upload notes, assessments, or session documents for{" "}
          {learner?.code ?? "the learner"}.
        </p>
      </div>

      <div className="v2-upload-layout">
        <Card className="v2-upload-main">
          <div className="v2-upload-learner">
            <span>{learner?.avatar ?? "🧒🏻"}</span>
            <div>
              <h2>
                {learner?.code ?? "Learner N-501"}{" "}
                <small>· Age {learner?.age ?? 7}</small>
              </h2>
              <div>{learner?.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div>
            </div>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            className="v2-visually-hidden"
            accept={ALLOWED_EXTENSIONS.join(",")}
            onChange={handleFileSelection}
          />
          <button
            className="v2-dropzone"
            type="button"
            onClick={() => fileInputRef.current?.click()}
          >
            <span>☁</span>
            <h2>Drag and drop files here</h2>
            <p>{ALLOWED_FILE_LABEL} · up to 10 MB</p>
          </button>

          <div className="v2-upload-security-note">
            Backend validation is required for every upload. Files are treated as
            untrusted and quarantined before future parsing.
          </div>

          <div className="v2-or">
            <span />
            or
            <span />
          </div>
          <button
            className="v2-paste-link"
            type="button"
            onClick={() => setShowPaste((value) => !value)}
          >
            ▣ &nbsp; Paste text instead
          </button>
          {showPaste && (
            <textarea
              autoFocus
              className="v2-paste-area"
              placeholder="Paste learner notes here…"
              onChange={(event) => {
                if (event.target.value.length === 1) {
                  onFeedback("Pasted text can be added as a learner record.");
                }
              }}
            />
          )}

          <h3>Recent uploads</h3>
          <div className="v2-upload-list">
            {records.map((record) => (
              <div key={record.id}>
                <span className={`v2-file-icon v2-file-${record.fileType.toLowerCase()}`}>
                  {record.fileType}
                </span>
                <strong>{record.fileName}</strong>
                <Tag tone="green">{record.status === "ready" ? "Ready" : "Uploaded"}</Tag>
                <small>{record.uploadedAt}</small>
                <button
                  onClick={() => onFeedback(`${record.fileName} is ready for review.`)}
                  aria-label={`More options for ${record.fileName}`}
                >
                  ⋮
                </button>
              </div>
            ))}
          </div>

          <div className="v2-upload-actions">
            <Button variant="secondary" onClick={() => void addMockFile()}>
              ＋ Add another file
            </Button>
            <Button onClick={onContinue}>Continue</Button>
          </div>
        </Card>

        <Card className="v2-next-panel">
          <h2>What happens next</h2>
          <ol>
            <li>
              <b>1</b>
              <span>▤</span>
              <strong>
                AI extracts strengths,
                <br />
                needs, and goals
              </strong>
            </li>
            <li>
              <b>2</b>
              <span>♙</span>
              <strong>
                You review and edit
                <br />
                learner information
              </strong>
            </li>
            <li>
              <b>3</b>
              <span>◎</span>
              <strong>
                You define the
                <br />
                lesson goal
              </strong>
            </li>
          </ol>
          <div className="v2-upload-complete">✓ &nbsp; {records.length} files uploaded</div>
        </Card>
      </div>
    </section>
  );
}

function validateSelectedFile(file: File): string | null {
  const lowerName = file.name.toLowerCase();
  const extension = `.${lowerName.split(".").pop() ?? ""}`;
  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    return `Unsupported file type. Please use ${ALLOWED_FILE_LABEL}.`;
  }
  if (/\.(exe|js|html|svg|bat|sh|php|zip|rar|7z|tar|gz|docm|xlsm|pptm)$/i.test(lowerName)) {
    return "This file type is not allowed for learner records.";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return "File is too large. Maximum upload size is 10 MB.";
  }
  return null;
}

function fileTypeFromName(name: string): string {
  const extension = name.split(".").pop()?.toUpperCase();
  return extension === "JPEG" ? "JPG" : extension || "TXT";
}
