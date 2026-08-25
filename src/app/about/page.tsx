import type { Metadata } from "next";
import Link from "next/link";
import { SITE, TOOLS } from "@/lib/site";

export const metadata: Metadata = {
  title: "About",
  description: `About ${SITE.name}.wiki — free everyday utilities with flagship craft.`,
};

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-14 sm:px-6">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-signal">About</p>
      <h1 className="mt-3 font-display text-4xl font-bold tracking-tight text-ink">
        {SITE.name}
        <span className="text-signal">.wiki</span>
      </h1>
      <p className="mt-4 text-lg text-muted-foreground">
        A small suite of everyday web utilities, rebuilt with the care of flagship software:
        precise typography, honest empty states, and privacy by default.
      </p>
      <div className="prose-like mt-8 space-y-4 text-foreground/90">
        <p>
          The original project shipped Video Downloader, a reading tool, and Telegram price
          alerts on Flask. This release elevates that product into a modern Next.js experience
          while keeping the same promise: free, open, and useful.
        </p>
        <p>
          <strong>Reader</strong> is deliberately a readability view for publicly available
          pages — the kind of craft Apple ships as Safari Reader — not a circumvention service.
        </p>
        <ul className="list-disc space-y-2 pl-5 text-muted-foreground">
          {TOOLS.map((t) => (
            <li key={t.slug}>
              <Link href={t.href} className="font-medium text-primary hover:underline">
                {t.name}
              </Link>
              {" — "}
              {t.blurb}
            </li>
          ))}
        </ul>
        <p>
          Source and contributions welcome on{" "}
          <a
            href={SITE.github}
            className="font-medium text-primary hover:underline"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
          .
        </p>
      </div>
    </div>
  );
}
