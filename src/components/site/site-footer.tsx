import Link from "next/link";
import { SITE, TOOLS } from "@/lib/site";

export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-border/70 bg-[#e8eef1]/70">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-12 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <p className="font-display text-lg font-semibold text-ink">
            {SITE.name}
            <span className="text-signal">.wiki</span>
          </p>
          <p className="mt-2 max-w-sm text-sm text-muted-foreground">
            Free utilities with flagship craft — no ads, no data selling, open to inspect.
          </p>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Tools
          </p>
          <ul className="mt-3 space-y-2 text-sm">
            {TOOLS.map((t) => (
              <li key={t.slug}>
                <Link href={t.href} className="text-foreground/80 hover:text-foreground">
                  {t.name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Project
          </p>
          <ul className="mt-3 space-y-2 text-sm">
            <li>
              <Link href="/about" className="text-foreground/80 hover:text-foreground">
                About
              </Link>
            </li>
            <li>
              <Link href="/privacy" className="text-foreground/80 hover:text-foreground">
                Privacy
              </Link>
            </li>
            <li>
              <Link href="/terms" className="text-foreground/80 hover:text-foreground">
                Terms
              </Link>
            </li>
            <li>
              <a
                href={SITE.github}
                target="_blank"
                rel="noopener noreferrer"
                className="text-foreground/80 hover:text-foreground"
              >
                GitHub
              </a>
            </li>
          </ul>
        </div>
      </div>
      <div className="border-t border-border/60 py-4 text-center text-xs text-muted-foreground">
        MIT licensed · Built for people, not engagement metrics
      </div>
    </footer>
  );
}
