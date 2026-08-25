import { ReactNode } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";

export function ToolShell({
  title,
  description,
  tag,
  children,
}: {
  title: string;
  description: string;
  tag?: string;
  children: ReactNode;
}) {
  return (
    <div className="relative mx-auto max-w-3xl px-4 py-10 sm:px-6 sm:py-14">
      <nav className="mb-6 flex items-center gap-1 text-sm text-muted-foreground" aria-label="Breadcrumb">
        <Link href="/" className="hover:text-foreground">
          Home
        </Link>
        <ChevronRight className="size-3.5" />
        <span className="text-foreground">{title}</span>
      </nav>

      <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-xl">
          <h1 className="font-display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
            {title}
          </h1>
          <p className="mt-2 text-base text-muted-foreground sm:text-lg">{description}</p>
        </div>
        {tag ? (
          <span className="rounded-md bg-accent px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-accent-foreground">
            {tag}
          </span>
        ) : null}
      </header>

      {children}
    </div>
  );
}
