import Link from "next/link";
import { SITE } from "@/lib/site";

export function BrandMark({
  size = "md",
  href = "/",
}: {
  size?: "sm" | "md" | "lg";
  href?: string;
}) {
  const sizes = {
    sm: { mark: 22, text: "text-lg" },
    md: { mark: 28, text: "text-xl" },
    lg: { mark: 40, text: "text-3xl md:text-5xl" },
  }[size];

  return (
    <Link
      href={href}
      className={`group inline-flex items-center gap-2.5 font-display font-semibold tracking-tight text-ink no-underline ${sizes.text}`}
    >
      <span
        className="relative grid place-items-center rounded-[0.55rem] bg-primary text-primary-foreground shadow-[0_8px_24px_-12px_rgba(13,61,58,0.7)] transition-transform duration-300 group-hover:-translate-y-0.5"
        style={{ width: sizes.mark + 10, height: sizes.mark + 10 }}
        aria-hidden
      >
        <svg
          width={sizes.mark * 0.62}
          height={sizes.mark * 0.62}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
        </svg>
      </span>
      <span>
        {SITE.name}
        <span className="text-signal">.wiki</span>
      </span>
    </Link>
  );
}
