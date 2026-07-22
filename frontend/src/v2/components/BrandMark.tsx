import { BRAND } from "../brand";

type Props = {
  className?: string;
  decorative?: boolean;
};

export function BrandMark({ className = "", decorative = true }: Props) {
  return (
    <img
      className={`v2-brand-mark ${className}`.trim()}
      src="/brand/atc-mark.svg"
      alt={decorative ? "" : `${BRAND.shortName} — ${BRAND.productName}`}
      aria-hidden={decorative || undefined}
    />
  );
}
