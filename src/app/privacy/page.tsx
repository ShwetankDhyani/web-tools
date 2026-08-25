import type { Metadata } from "next";

export const metadata: Metadata = { title: "Privacy" };

export default function PrivacyPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-14 sm:px-6">
      <h1 className="font-display text-3xl font-bold text-ink">Privacy</h1>
      <div className="mt-6 space-y-4 text-sm leading-relaxed text-muted-foreground">
        <p>
          WebTools.wiki does not sell personal data and does not run advertising trackers on these
          tools.
        </p>
        <p>
          <strong className="text-foreground">Video Downloader</strong> and{" "}
          <strong className="text-foreground">Reader</strong> do not require an account. Submitted
          URLs are processed to fulfill your request. Temporary download files are deleted after a
          short TTL.
        </p>
        <p>
          <strong className="text-foreground">Price Tracker</strong> stores your Telegram username,
          tracked product URLs, and price history so alerts can be delivered. Sign-in uses a
          short-lived one-time code.
        </p>
        <p>
          Server logs may include IP addresses and error diagnostics for security and reliability.
          Self-hosting keeps all of this under your control.
        </p>
      </div>
    </div>
  );
}
