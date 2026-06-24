import type { ReactNode } from "react";

type StatusMessageProps = {
  tone: "error" | "success" | "hint";
  children: ReactNode;
};

export function StatusMessage({ tone, children }: StatusMessageProps) {
  return <p className={tone}>{children}</p>;
}
