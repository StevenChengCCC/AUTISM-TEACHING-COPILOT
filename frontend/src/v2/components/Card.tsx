import type { HTMLAttributes, ReactNode } from "react";

type Props = HTMLAttributes<HTMLDivElement> & { children: ReactNode };

export function Card({ children, className = "", ...props }: Props) {
  return <div className={`v2-card ${className}`} {...props}>{children}</div>;
}
