import type { ReactNode } from "react";

type StatusMessageProps = {
  tone: "error" | "success" | "hint";
  children: ReactNode;
};

export function StatusMessage({ tone, children }: StatusMessageProps) {
  return (
    <p className={tone}>
      {tone === "error" && (
        <svg className="msgicon" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7.5v5" />
          <circle cx="12" cy="16.2" r="0.6" fill="currentColor" stroke="none" />
        </svg>
      )}
      {children}
    </p>
  );
}
