import { useEffect, useMemo, useState } from "react";
import { lessonKitApi } from "../api/lessonKitApi";
import type {
  ExportJob,
  HandoffSectionSelection,
  LessonPackage,
  TeacherHandoffExportInput,
} from "../types";
import { Button } from "./Button";
import { Card } from "./Card";

const defaultSections: HandoffSectionSelection = {
  learnerOverview: true,
  teachingStrategies: true,
  activeGoals: true,
  progress: false,
  recentSessions: true,
  lessonPackages: true,
  approvedMaterials: true,
  transitionNotes: true,
};

const sectionLabels: Partial<Record<keyof HandoffSectionSelection, string>> = {
  learnerOverview: "Approved learner overview",
  teachingStrategies: "Approved teaching strategies",
  activeGoals: "Active goals",
  recentSessions: "Recent sessions",
  lessonPackages: "Approved lesson package",
  approvedMaterials: "Approved materials",
  transitionNotes: "Teacher transition notes",
};

export function TeacherHandoffExportPanel({
  lessonPackage,
  onPackageChange,
  onFeedback,
}: {
  lessonPackage: LessonPackage;
  onPackageChange: (value: LessonPackage) => void;
  onFeedback: (message: string) => void;
}) {
  const [sections, setSections] = useState(defaultSections);
  const startDate = "";
  const endDate = "";
  const [notes, setNotes] = useState("");
  const [pageSize, setPageSize] = useState<"Letter" | "A4">("Letter");
  const [includePrintables, setIncludePrintables] = useState(true);
  const [selectedMaterialIds, setSelectedMaterialIds] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [jobs, setJobs] = useState<ExportJob[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const approvedMaterials = useMemo(
    () => lessonPackage.materials.filter((item) => item.status === "approved"),
    [lessonPackage.materials],
  );

  const refresh = async () => {
    try {
      setJobs(await lessonKitApi.getHandoffExports(lessonPackage.learnerId));
    } catch {
      // Export history is supplementary; the page remains usable if unavailable.
    }
  };

  useEffect(() => {
    void refresh();
  }, [lessonPackage.learnerId]);

  useEffect(() => {
    setSelectedMaterialIds((current) => {
      const available = new Set(approvedMaterials.map((item) => item.id));
      const retained = current.filter((id) => available.has(id));
      return retained.length ? retained : [...available];
    });
  }, [approvedMaterials]);

  useEffect(() => {
    const active = jobs.filter((job) => job.status === "pending" || job.status === "processing");
    if (!active.length) return;
    const timer = window.setInterval(() => {
      void Promise.all(active.map((job) => lessonKitApi.getHandoffExport(job.exportId)))
        .then((updates) => setJobs((current) => current.map((job) => updates.find((item) => item.exportId === job.exportId) ?? job)))
        .catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [jobs]);

  async function generate() {
    if (!confirmed) return;
    setBusy(true);
    setError("");
    try {
      const payload: TeacherHandoffExportInput = {
        sections,
        dateRange: { startDate: startDate || null, endDate: endDate || null },
        sessionIds: [],
        packageIds: lessonPackage.status === "approved" ? [lessonPackage.id] : [],
        materialIds: selectedMaterialIds,
        transitionNotes: notes,
        includePrintableMaterials: includePrintables,
        pageSize,
        orientation: "portrait",
        reviewedConfirmation: true,
      };
      const job = await lessonKitApi.createHandoffExport(lessonPackage.learnerId, payload);
      setJobs((current) => [job, ...current.filter((item) => item.exportId !== job.exportId)]);
      onFeedback(job.status === "completed" ? "Teacher handoff export is ready." : job.message);
      if (job.status === "failed") setError(job.message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Export generation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function download(job: ExportJob) {
    try {
      const result = await lessonKitApi.getHandoffExportDownload(job.exportId);
      window.location.assign(result.downloadUrl);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Download could not be prepared.");
    }
  }

  async function retry(job: ExportJob) {
    setBusy(true);
    try {
      const replacement = await lessonKitApi.retryHandoffExport(job.exportId);
      setJobs((current) => [replacement, ...current]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Retry failed.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(job: ExportJob) {
    if (!window.confirm("Delete this private export? This cannot be undone.")) return;
    const deleted = await lessonKitApi.deleteHandoffExport(job.exportId);
    setJobs((current) => current.map((item) => item.exportId === deleted.exportId ? deleted : item));
  }

  const readyForApprovedContent = lessonPackage.status === "approved" &&
    lessonPackage.materials.every((item) => item.status === "approved");

  return (
    <Card className="v2-handoff-export">
      <header>
        <div><small>PRIVATE EXPORT</small><h2>Teacher Handoff</h2></div>
        <span className={readyForApprovedContent ? "is-ready" : ""}>
          {readyForApprovedContent ? "Approved content ready" : "Approval needed"}
        </span>
      </header>

      {!readyForApprovedContent && (
        <div className="v2-handoff-approval">
          <p>Only individually reviewed and approved material revisions are included. Complete review in Review Printable Content first.</p>
        </div>
      )}

      <fieldset>
        <legend>Select handoff sections</legend>
        <div className="v2-handoff-options">
          {(Object.keys(sectionLabels) as (keyof HandoffSectionSelection)[]).map((key) => (
            <label key={key}>
              <input type="checkbox" checked={sections[key]} onChange={() => setSections((current) => ({ ...current, [key]: !current[key] }))} />
              {sectionLabels[key]}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="v2-handoff-fields">
        <label>Page size<select value={pageSize} onChange={(event) => setPageSize(event.target.value as "Letter" | "A4")}><option>Letter</option><option>A4</option></select></label>
      </div>
      <label className="v2-handoff-notes">Transition notes<textarea value={notes} maxLength={5000} onChange={(event) => setNotes(event.target.value)} placeholder="Add teacher-authored context for the receiving team." /></label>
      {approvedMaterials.length > 0 && <fieldset><legend>Select approved materials</legend><div className="v2-handoff-materials">{approvedMaterials.map((material) => <label key={material.id}><input type="checkbox" checked={selectedMaterialIds.includes(material.id)} onChange={() => setSelectedMaterialIds((current) => current.includes(material.id) ? current.filter((id) => id !== material.id) : [...current, material.id])}/>{material.title}</label>)}</div></fieldset>}
      <label className="v2-handoff-inline"><input type="checkbox" checked={includePrintables} onChange={() => setIncludePrintables((value) => !value)} />Include approved printable material PDFs</label>

      <details>
        <summary>Review default exclusions and redaction</summary>
        <ul>
          <li>Original uploads and raw extracted text</li>
          <li>Unapproved AI drafts and internal conversations</li>
          <li>System prompts, provider metadata, audit logs, and credentials</li>
          <li>Deleted content and unnecessary contact details</li>
        </ul>
      </details>
      <div className="v2-handoff-preview">
        <strong>Bundle preview</strong>
        <small>{Object.values(sections).filter(Boolean).length} sections · {selectedMaterialIds.length} approved materials</small>
        <span>handoff-summary.pdf</span><span>handoff-data.json</span><span>README.txt</span>
      </div>
      <label className="v2-handoff-confirm">
        <input type="checkbox" checked={confirmed} onChange={() => setConfirmed((value) => !value)} />
        I reviewed this export and confirm that it is intended for an authorized educational handoff.
      </label>
      {error && <p className="v2-handoff-error" role="alert">{error}</p>}
      <Button fullWidth disabled={!confirmed || busy} onClick={() => void generate()}>{busy ? "Preparing…" : "Generate Private ZIP"}</Button>

      {jobs.length > 0 && <div className="v2-export-history"><h3>Export history</h3>{jobs.slice(0, 5).map((job) => <article key={job.exportId}>
        <div><strong>{job.fileName}</strong><small>{job.status} · {job.progressPercent}% · {new Date(job.requestedAt).toLocaleString()}</small></div>
        <div>{job.status === "completed" && <button onClick={() => void download(job)}>Download</button>}{(job.status === "failed" || job.status === "expired") && <button onClick={() => void retry(job)}>Retry</button>}{job.status !== "deleted" && <button onClick={() => void remove(job)}>Delete</button>}</div>
      </article>)}</div>}
      <p className="v2-handoff-disclaimer">Teacher confirmation supports the handoff workflow; it is not a claim of legal compliance.</p>
    </Card>
  );
}
