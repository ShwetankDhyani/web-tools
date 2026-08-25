import type { Metadata } from "next";

export const metadata: Metadata = { title: "Terms" };

export default function TermsPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-14 sm:px-6">
      <h1 className="font-display text-3xl font-bold text-ink">Terms of use</h1>
      <div className="mt-6 space-y-4 text-sm leading-relaxed text-muted-foreground">
        <p>
          WebTools.wiki is provided free of charge, as-is, without warranty. Use the tools
          responsibly and in accordance with the terms of any third-party sites you access.
        </p>
        <p>
          Video downloading is intended for personal use of content you have the right to obtain.
          Reader extracts publicly available HTML into a reading view; it is not a service for
          unauthorized access to paid content.
        </p>
        <p>
          Do not abuse rate limits, attempt to probe internal networks, or use the service to harm
          others. We may throttle or block abusive traffic.
        </p>
        <p>The software is released under the MIT License.</p>
      </div>
    </div>
  );
}
