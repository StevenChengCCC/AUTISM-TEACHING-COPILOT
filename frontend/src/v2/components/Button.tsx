import type { ButtonHTMLAttributes, ReactNode } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  variant?: "primary" | "secondary" | "ghost";
  fullWidth?: boolean;
};

export function Button({ children, variant = "primary", fullWidth = false, className = "", ...props }: Props) {
  return (
    <button className={`v2-button v2-button--${variant} ${fullWidth ? "v2-button--full" : ""} ${className}`} {...props}>
      {children}
    </button>
  );
}
