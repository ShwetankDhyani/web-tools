"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowUpRight, Download, BookOpenText, BellRing } from "lucide-react";
import { BrandMark } from "@/components/site/brand-mark";
import { Button } from "@/components/ui/button";
import { SITE, TOOLS } from "@/lib/site";

const icons = {
  video: Download,
  reader: BookOpenText,
  prices: BellRing,
} as const;

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: 0.08 * i, duration: 0.55, ease: [0.22, 1, 0.36, 1] as const },
  }),
};

export default function HomePage() {
  return (
    <div className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 grid-atmosphere" aria-hidden />

      <section className="relative mx-auto flex min-h-[calc(100svh-4rem)] max-w-6xl flex-col justify-center px-4 pb-16 pt-10 sm:px-6 md:pt-6">
        <motion.div
          initial="hidden"
          animate="show"
          className="relative z-10 max-w-3xl"
        >
          <motion.div custom={0} variants={fadeUp}>
            <BrandMark size="lg" />
          </motion.div>
          <motion.h1
            custom={1}
            variants={fadeUp}
            className="mt-8 font-display text-4xl font-bold leading-[1.05] tracking-tight text-ink text-balance sm:text-5xl md:text-6xl"
          >
            Everyday tools,
            <br />
            <span className="text-primary">flagship polish.</span>
          </motion.h1>
          <motion.p
            custom={2}
            variants={fadeUp}
            className="mt-5 max-w-xl text-lg text-muted-foreground sm:text-xl"
          >
            {SITE.tagline} Free forever — video, reading, and price alerts without the noise.
          </motion.p>
          <motion.div custom={3} variants={fadeUp} className="mt-8 flex flex-wrap gap-3">
            <Button
              size="lg"
              className="rounded-full px-6"
              render={<Link href="/video" />}
            >
              Open Video Downloader
              <ArrowUpRight className="size-4" />
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="rounded-full bg-white/50 px-6"
              render={<Link href="/reader" />}
            >
              Try Reader
            </Button>
          </motion.div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 24 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ delay: 0.35, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="pointer-events-none absolute -right-8 bottom-8 hidden h-[420px] w-[420px] md:block lg:right-0 lg:h-[480px] lg:w-[480px]"
          aria-hidden
        >
          <div className="absolute inset-0 rounded-full bg-[conic-gradient(from_210deg_at_50%_50%,rgba(17,153,142,0.28),rgba(59,109,140,0.12),rgba(196,92,38,0.16),rgba(17,153,142,0.28))] blur-2xl" />
          <div className="absolute inset-12 rounded-full border border-white/50 bg-white/40 shadow-[0_30px_80px_-40px_rgba(16,24,28,0.45)] backdrop-blur-md" />
          <div className="absolute inset-[4.5rem] rounded-full border border-dashed border-primary/25" />
          <div className="absolute left-1/2 top-1/2 size-24 -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-primary text-primary-foreground shadow-xl">
            <div className="grid h-full place-items-center font-display text-xs font-semibold tracking-[0.18em]">
              TOOLS
            </div>
          </div>
        </motion.div>
      </section>

      <section className="relative mx-auto max-w-6xl px-4 pb-20 sm:px-6">
        <div className="mb-8 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-signal">
              Three essentials
            </p>
            <h2 className="mt-2 font-display text-2xl font-semibold text-ink sm:text-3xl">
              Pick a tool. Get it done.
            </h2>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {TOOLS.map((tool, i) => {
            const Icon = icons[tool.accent as keyof typeof icons];
            return (
              <motion.div
                key={tool.slug}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ delay: i * 0.08, duration: 0.5 }}
              >
                <Link
                  href={tool.href}
                  className="group block h-full rounded-2xl p-6 no-underline surface-panel transition-transform duration-300 hover:-translate-y-1"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="grid size-11 place-items-center rounded-xl bg-primary text-primary-foreground">
                      <Icon className="size-5" />
                    </span>
                    <span className="rounded-md bg-accent px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-accent-foreground">
                      {tool.tag}
                    </span>
                  </div>
                  <h3 className="mt-5 font-display text-xl font-semibold text-ink">
                    {tool.name}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {tool.blurb}
                  </p>
                  <span className="mt-5 inline-flex items-center gap-1 text-sm font-semibold text-primary">
                    Open tool
                    <ArrowUpRight className="size-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                  </span>
                </Link>
              </motion.div>
            );
          })}
        </div>
      </section>

      <section className="border-y border-border/70 bg-white/40">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-14 sm:px-6 md:grid-cols-3">
          {[
            {
              title: "Free to use",
              body: "No premium tiers on these tools. The product is the gift.",
            },
            {
              title: "Privacy-minded",
              body: "Video and Reader need no account. Prices only uses your Telegram username for alerts.",
            },
            {
              title: "Open source",
              body: "Inspect the code, self-host, or contribute. Transparency is a feature.",
            },
          ].map((item) => (
            <div key={item.title}>
              <h3 className="font-display text-lg font-semibold text-ink">{item.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{item.body}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
