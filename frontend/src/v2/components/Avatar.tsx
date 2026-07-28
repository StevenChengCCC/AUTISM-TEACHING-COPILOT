import type { CSSProperties } from "react";

const learnerAvatars = [
  "/avatars/learner-blue.png",
  "/avatars/learner-coral.png",
  "/avatars/learner-mint.png",
];

function stableAvatarIndex(value: string) {
  return [...value].reduce((total, character) => total + character.charCodeAt(0), 0) % learnerAvatars.length;
}

function isImageSource(value?: string) {
  return Boolean(value && (/^(?:https?:|data:|\/)/.test(value)));
}

export function LearnerAvatar({
  learnerId,
  avatar,
  alt = "",
  size = 52,
  className = "",
}: {
  learnerId: string;
  avatar?: string;
  alt?: string;
  size?: number;
  className?: string;
}) {
  const source = isImageSource(avatar)
    ? avatar
    : learnerAvatars[stableAvatarIndex(learnerId || "new-learner")];
  const style = { "--avatar-size": `${size}px` } as CSSProperties;
  return <span className={`v2-illustrated-avatar ${className}`} style={style}>
    <img src={source} alt={alt} />
  </span>;
}

export function TeacherAvatar({
  alt = "",
  size = 44,
  className = "",
}: {
  alt?: string;
  size?: number;
  className?: string;
}) {
  const style = { "--avatar-size": `${size}px` } as CSSProperties;
  return <span className={`v2-illustrated-avatar v2-illustrated-avatar--teacher ${className}`} style={style}>
    <img src="/avatars/teacher.png" alt={alt} />
  </span>;
}
