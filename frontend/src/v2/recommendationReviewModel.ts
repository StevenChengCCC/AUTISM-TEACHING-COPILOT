import type {
  NextSessionRecommendation,
  ReviewNextSessionRecommendationInput,
} from "./types";

export function recommendationDisplayText(
  recommendation: NextSessionRecommendation,
): string {
  return recommendation.status === "edited" &&
    recommendation.teacherEditedText !== null
    ? recommendation.teacherEditedText
    : recommendation.recommendation;
}

export function recommendationReviewInput(
  recommendation: NextSessionRecommendation,
  action: "accepted" | "edited" | "rejected",
  teacherEditedText?: string,
): ReviewNextSessionRecommendationInput {
  if (action === "edited" && !(teacherEditedText ?? "").trim()) {
    throw new Error("Enter the teacher-edited recommendation before saving.");
  }
  return {
    action,
    expectedVersion: recommendation.version,
    ...(action === "edited" ? { teacherEditedText } : {}),
  };
}

export function recommendationStatusLabel(
  recommendation: NextSessionRecommendation,
): string {
  if (recommendation.status === "pending") return "Awaiting teacher review";
  if (recommendation.status === "accepted") return "Accepted by teacher";
  if (recommendation.status === "edited") return "Edited by teacher";
  return "Rejected by teacher — excluded from future planning inputs";
}
