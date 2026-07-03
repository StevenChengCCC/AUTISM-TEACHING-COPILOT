import type { ReactNode } from "react";

export function Tag({ children, tone = "blue" }: { children: ReactNode; tone?: "blue" | "green" | "purple" | "amber" | "gray" }) {
  return <span className={`v2-tag v2-tag--${tone}`}>{children}</span>;
}
