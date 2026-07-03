import type { LearnerProfile } from "../types";
import { Tag } from "./Tag";

export function LearnerContextBar({ learner, onViewProfile, onChangeLearner }: { learner: LearnerProfile; onViewProfile: () => void; onChangeLearner: () => void }) {
  return (
    <div className="v2-learner-context">
      <span className="v2-learner-avatar">{learner.avatar}</span>
      <strong>{learner.code}</strong><span>• Age {learner.age}</span>
      {learner.supportNeeds.slice(0, 2).map((need) => <Tag tone={need.includes("attention") || need.includes("Attention") ? "amber" : "blue"} key={need}>{need}</Tag>)}
      {learner.interests.slice(0, 1).map((interest) => <Tag tone="green" key={interest}>{interest}</Tag>)}
      <div className="v2-context-actions">
        <button onClick={onViewProfile}>View profile</button>
        <button onClick={onChangeLearner}>Change learner</button>
      </div>
    </div>
  );
}
