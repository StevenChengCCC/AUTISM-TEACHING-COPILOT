import { useEffect, useState } from "react";
import { lessonKitApi } from "../api/lessonKitApi";
import {
  recommendationDisplayText,
  recommendationReviewInput,
  recommendationStatusLabel,
} from "../recommendationReviewModel";
import type { NextSessionRecommendation } from "../types";

export function NextSessionRecommendationsPanel({
  learnerId,
  goalId,
  goalRevision,
}: {
  learnerId: string;
  goalId: string;
  goalRevision: number;
}) {
  const [items, setItems] = useState<NextSessionRecommendation[]>([]);
  const [index, setIndex] = useState(0);
  const [editing, setEditing] = useState(false);
  const [teacherText, setTeacherText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    setItems([]);
    setIndex(0);
    setEditing(false);
    setError("");
    void lessonKitApi
      .getNextSessionRecommendations(learnerId, goalId, goalRevision)
      .then(setItems)
      .catch((reason) =>
        setError(
          reason instanceof Error
            ? reason.message
            : "Recommendations could not be loaded.",
        ),
      );
  }, [learnerId, goalId, goalRevision]);

  const current = items[index];
  const generate = async () => {
    setBusy(true);
    setError("");
    try {
      const generated = await lessonKitApi.generateNextSessionRecommendations(
        learnerId,
        goalId,
        goalRevision,
      );
      setItems(generated);
      setIndex(0);
      setNotice(
        "Suggestions were derived from recorded evidence. Nothing was changed automatically.",
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Recommendations could not be generated.",
      );
    } finally {
      setBusy(false);
    }
  };
  const review = async (action: "accepted" | "edited" | "rejected") => {
    if (!current) return;
    setBusy(true);
    setError("");
    try {
      const updated = await lessonKitApi.reviewNextSessionRecommendation(
        current.id,
        recommendationReviewInput(current, action, teacherText),
      );
      setItems((values) =>
        values.map((item) => (item.id === updated.id ? updated : item)),
      );
      setEditing(false);
      setNotice(
        action === "rejected"
          ? "Rejected. This recommendation will not be used as a future planning input."
          : "Teacher review saved. No LessonSpec, profile, kit, or material was changed.",
      );
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Review could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      id="next-session-recommendations"
      className="v2-next-recommendations"
      aria-labelledby="next-recommendations-heading"
    >
      <header>
        <div>
          <small>Teacher-reviewed planning support</small>
          <h4 id="next-recommendations-heading">Next-session suggestions</h4>
        </div>
        <button type="button" disabled={busy} onClick={() => void generate()}>
          {items.length
            ? "Refresh from recorded evidence"
            : "Generate suggestions"}
        </button>
      </header>
      <p>
        Suggestions cite structured observations and require individual teacher
        review. They never change the learner profile, lesson, or materials by
        themselves.
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {!current && !busy && (
        <p>No next-session suggestions have been generated for this goal.</p>
      )}
      {current && (
        <article>
          <div className="v2-recommendation-position">
            <button
              type="button"
              disabled={index === 0}
              aria-label="Previous recommendation"
              onClick={() => {
                setIndex((value) => value - 1);
                setEditing(false);
              }}
            >
              Previous
            </button>
            <span>
              Recommendation {index + 1} of {items.length}
            </span>
            <button
              type="button"
              disabled={index === items.length - 1}
              aria-label="Next recommendation"
              onClick={() => {
                setIndex((value) => value + 1);
                setEditing(false);
              }}
            >
              Next
            </button>
          </div>
          <small>{current.type.replace(/_/g, " ")}</small>
          <h5>{current.title}</h5>
          <p className="v2-recommendation-copy">
            {recommendationDisplayText(current)}
          </p>
          <p>
            <b>Confidence: {current.confidence}.</b> {current.confidenceReason}
          </p>
          <p className={`v2-recommendation-status is-${current.status}`}>
            {recommendationStatusLabel(current)}
          </p>
          <details>
            <summary>View cited evidence ({current.evidence.length})</summary>
            <ul>
              {current.evidence.map((evidence, evidenceIndex) => (
                <li
                  key={`${evidence.sessionId}-${evidence.metricPath}-${evidenceIndex}`}
                >
                  <strong>{evidence.sessionId}</strong>
                  <span>{evidence.description}</span>
                  <small>
                    {evidence.metricPath} · observed:{" "}
                    {String(evidence.observedValue)}
                    {evidence.contextLabel ? ` · ${evidence.contextLabel}` : ""}
                  </small>
                </li>
              ))}
            </ul>
          </details>
          <details>
            <summary>View potentially affected fields</summary>
            <p>
              LessonSpec: {current.affectedLessonSpecPaths.join(", ") || "none"}
            </p>
            <p>Materials: {current.affectedMaterialIds.join(", ") || "none"}</p>
            <p>
              Material types:{" "}
              {current.affectedMaterialTypes.join(", ") || "none"}
            </p>
          </details>
          {editing ? (
            <div className="v2-recommendation-edit">
              <label>
                Teacher-edited recommendation
                <textarea
                  value={teacherText}
                  onChange={(event) => setTeacherText(event.target.value)}
                />
              </label>
              <div>
                <button
                  type="button"
                  disabled={busy || !teacherText.trim()}
                  onClick={() => void review("edited")}
                >
                  Save exact wording
                </button>
                <button type="button" onClick={() => setEditing(false)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="v2-recommendation-actions">
              <button
                type="button"
                disabled={busy}
                onClick={() => void review("accepted")}
              >
                Accept this recommendation
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  setTeacherText(recommendationDisplayText(current));
                  setEditing(true);
                }}
              >
                Edit wording
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void review("rejected")}
              >
                Reject
              </button>
            </div>
          )}
        </article>
      )}
    </section>
  );
}
