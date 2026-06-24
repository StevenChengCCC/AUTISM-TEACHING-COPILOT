import { useState } from "react";
import { StatusMessage } from "../components/StatusMessage";
import { api } from "../api/client";
import type {
  ChildProfile,
  ImageCandidate,
  ImagePipelineResult,
  TeachingGoal,
} from "../types";

type Props = {
  child: ChildProfile | null;
  goal: TeachingGoal | null;
  imageResult: ImagePipelineResult | null;
  onImageResultChange: (result: ImagePipelineResult | null) => void;
  onConfirmedImagesChange: (images: ImageCandidate[]) => void;
};

export function ImagePipelineReviewPage({
  child,
  goal,
  imageResult,
  onImageResultChange,
  onConfirmedImagesChange,
}: Props) {
  const [approvedIndexes, setApprovedIndexes] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function runPipeline() {
    if (!child || !goal) {
      setError("Select a child and teaching goal first.");
      return;
    }
    setLoading(true);
    setError("");
    setSuccess("");
    setApprovedIndexes([]);
    try {
      const result = await api.runImagePipeline({
        child_id: child.id,
        target_skill: goal.target_skill,
        concept: goal.concept || goal.target_skill,
        needed_count: 8,
        prefer_real_photos: true,
        variation_requirements: [
          "visual_variation",
          "physical_object_variation",
          "environment_variation",
        ],
      });
      onImageResultChange(result);
      setSuccess("Image candidates ready for teacher review.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to run image pipeline",
      );
    } finally {
      setLoading(false);
    }
  }

  async function confirmImages() {
    if (!imageResult || !goal) return;
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      const saved = await api.confirmImages({
        candidates: imageResult.candidates,
        approved_indexes: approvedIndexes,
        skill_target: goal.target_skill,
        concept: goal.concept || goal.target_skill,
      });
      onConfirmedImagesChange(saved);
      setSuccess(`${saved.length} image asset(s) saved to the library.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to confirm images");
    } finally {
      setLoading(false);
    }
  }

  function toggleApproved(index: number) {
    setApprovedIndexes((current) =>
      current.includes(index)
        ? current.filter((item) => item !== index)
        : [...current, index],
    );
  }

  return (
    <section className="card">
      <h2>Image Pipeline Review</h2>
      {loading && <StatusMessage tone="hint">Loading...</StatusMessage>}
      {error && <StatusMessage tone="error">{error}</StatusMessage>}
      {success && <StatusMessage tone="success">{success}</StatusMessage>}
      <div className="pipeline">
        <span>Reuse</span>
        <b>→</b>
        <span>Search</span>
        <b>→</b>
        <span>Generate/Mock</span>
        <b>→</b>
        <span>Teacher Review</span>
      </div>
      <button
        className="primary"
        disabled={loading || !child || !goal}
        onClick={runPipeline}
      >
        Run Image Pipeline
      </button>
      {imageResult && (
        <>
          <p className="hint">Strategy: {imageResult.strategy_used}</p>
          {imageResult.notes.map((note) => (
            <p className="hint" key={note}>
              {note}
            </p>
          ))}
          <div className="candidateGrid">
            {imageResult.candidates.map((image, index) => (
              <div
                className={`candidate ${approvedIndexes.includes(index) ? "approved" : ""}`}
                key={`${image.title}-${index}`}
                onClick={() => toggleApproved(index)}
              >
                {image.thumbnail_url ? (
                  <img src={image.thumbnail_url} alt={image.title} />
                ) : (
                  <div className="placeholder">IMG</div>
                )}
                <strong>{image.title}</strong>
                <small>
                  {image.source_type} · {image.variation_type} · score{" "}
                  {image.quality_score}
                </small>
                {image.reason && <small>{image.reason}</small>}
                {image.generation_prompt && (
                  <pre>{image.generation_prompt}</pre>
                )}
              </div>
            ))}
          </div>
          <button
            className="primary"
            disabled={approvedIndexes.length === 0 || loading}
            onClick={confirmImages}
          >
            Confirm Selected Images
          </button>
        </>
      )}
    </section>
  );
}
