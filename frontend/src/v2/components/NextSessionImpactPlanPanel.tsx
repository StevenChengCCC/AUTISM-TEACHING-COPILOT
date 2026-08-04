import { useState } from "react";
import type { ReactNode } from "react";
import { lessonKitApi } from "../api/lessonKitApi";
import type {
  NextSessionMaterialImpactPlan,
  UpdateNextSessionPlanInput,
} from "../types";

export function NextSessionImpactPlanPanel({
  previousPackageId,
}: {
  previousPackageId: string;
}) {
  const [plan, setPlan] = useState<NextSessionMaterialImpactPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const preview = async () => {
    setBusy(true);
    setError("");
    try {
      const previous = await lessonKitApi.getLessonPackage(previousPackageId);
      const value = await lessonKitApi.createNextSessionPlan(
        previousPackageId,
        previous.version ?? 1,
      );
      setPlan(value);
      setNotice(
        "Impact preview created. No historical lesson or material has been changed.",
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The next-session impact preview could not be created.",
      );
    } finally {
      setBusy(false);
    }
  };

  const override = async (
    input: Omit<UpdateNextSessionPlanInput, "expectedVersion">,
  ) => {
    if (!plan) return;
    setBusy(true);
    setError("");
    try {
      const value = await lessonKitApi.updateNextSessionPlan(plan.id, {
        ...input,
        expectedVersion: plan.version,
      });
      setPlan(value);
      setNotice("Teacher override saved with its reason and revision.");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The material decision could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  };

  const createPackage = async () => {
    if (!plan) return;
    setBusy(true);
    setError("");
    try {
      const created = await lessonKitApi.createNextSessionPackage(
        plan.id,
        plan.version,
      );
      setPlan(await lessonKitApi.getNextSessionPlan(plan.id));
      setNotice(
        `Next-session kit ${created.id} created. Reused revisions remain approved; revised items require review.`,
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The selective next-session kit could not be created.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      className="v2-next-session-impact"
      aria-labelledby="next-session-impact-heading"
    >
      <header>
        <div>
          <small>Explicit selective-update step</small>
          <h4 id="next-session-impact-heading">Next-session material impact</h4>
        </div>
        {!plan && (
          <button type="button" disabled={busy} onClick={() => void preview()}>
            Preview LessonSpec and material changes
          </button>
        )}
      </header>
      <p>
        Only accepted or teacher-edited recommendations are planning inputs.
        Review what can be reused before creating a new immutable kit revision.
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {plan && (
        <>
          <div className="v2-impact-summary">
            <strong>
              LessonSpec revision{" "}
              {plan.proposedLessonSpecRevision.previousLessonSpecRevision}
              {" → "}
              {plan.proposedLessonSpecRevision.lessonSpec.revision}
            </strong>
            <span>
              {plan.proposedLessonSpecRevision.acceptedRecommendationIds.length}{" "}
              reviewed recommendation(s) included
            </span>
            <span>
              Progress series:{" "}
              {plan.proposedLessonSpecRevision.goalSeriesBoundary === "new"
                ? "new goal boundary"
                : "continue compatible goal series"}
            </span>
          </div>

          <ImpactCategory
            title="Reuse unchanged"
            count={plan.reusableMaterials.length}
          >
            {plan.reusableMaterials.map((item) => (
              <article key={item.materialId}>
                <h5>{item.title}</h5>
                <p>{item.reasonReusable}</p>
                <small>
                  Revision {item.materialRevision} · exact approved lineage
                  retained
                </small>
                <button
                  type="button"
                  disabled={busy || plan.status !== "proposed"}
                  onClick={() =>
                    void override({
                      action: "force_regenerate",
                      materialId: item.materialId,
                      reason:
                        "Teacher chose a fresh revision after reviewing the reuse rationale.",
                    })
                  }
                >
                  Regenerate this material instead
                </button>
              </article>
            ))}
          </ImpactCategory>

          <ImpactCategory title="Revise" count={plan.materialsToRevise.length}>
            {plan.materialsToRevise.map((item) => (
              <article key={item.materialId}>
                <h5>{item.title}</h5>
                <p>{item.reason}</p>
                <small>
                  Affected fields:{" "}
                  {item.affectedFields.join(", ") ||
                    "teacher-requested refresh"}
                </small>
                {item.safeToKeepExisting && (
                  <button
                    type="button"
                    disabled={busy || plan.status !== "proposed"}
                    onClick={() =>
                      void override({
                        action: "keep_existing",
                        materialId: item.materialId,
                        reason:
                          "Teacher confirmed the existing semantic content still fits.",
                      })
                    }
                  >
                    Keep existing compatible revision
                  </button>
                )}
              </article>
            ))}
          </ImpactCategory>

          <ImpactCategory title="New" count={plan.newMaterialsRequired.length}>
            {plan.newMaterialsRequired.map((item) => (
              <article key={item.materialType}>
                <h5>{item.materialType.replace(/_/g, " ")}</h5>
                <p>{item.reason}</p>
                {!item.required && (
                  <button
                    type="button"
                    disabled={busy || plan.status !== "proposed"}
                    onClick={() =>
                      void override({
                        action: "reject_new",
                        materialType: item.materialType,
                        reason:
                          "Teacher declined this optional addition for the next session.",
                      })
                    }
                  >
                    Exclude optional addition
                  </button>
                )}
              </article>
            ))}
          </ImpactCategory>

          <ImpactCategory title="Remove" count={plan.materialsToRemove.length}>
            {plan.materialsToRemove.map((item) => (
              <article key={item.materialId}>
                <h5>{item.title}</h5>
                <p>{item.reason}</p>
              </article>
            ))}
          </ImpactCategory>

          <ImpactCategory title="Blocking" count={plan.blockingIssues.length}>
            {plan.blockingIssues.map((item) => (
              <p key={item}>{item}</p>
            ))}
          </ImpactCategory>

          <div className="v2-impact-actions">
            <button
              type="button"
              onClick={() =>
                document
                  .getElementById("next-session-recommendations")
                  ?.scrollIntoView({ behavior: "smooth" })
              }
            >
              Return to recommendation review
            </button>
            <button
              type="button"
              disabled={
                busy ||
                plan.blockingIssues.length > 0 ||
                plan.status !== "proposed"
              }
              onClick={() => void createPackage()}
            >
              Create selective next-session kit
            </button>
          </div>
        </>
      )}
    </section>
  );
}

function ImpactCategory({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: ReactNode;
}) {
  return (
    <details open={count > 0}>
      <summary>
        {title} ({count})
      </summary>
      <div>{count ? children : <p>No materials in this category.</p>}</div>
    </details>
  );
}
