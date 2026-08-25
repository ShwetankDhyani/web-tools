export const SITE = {
  name: "WebTools",
  domain: "webtools.wiki",
  tagline: "Everyday utilities, engineered like flagship software.",
  description:
    "Download videos, read articles cleanly, and track prices with Telegram alerts — free, private, and open source.",
  github: "https://github.com/ShwetankDhyani/web-tools",
  url: "https://webtools.wiki",
} as const;

export const TOOLS = [
  {
    slug: "video",
    href: "/video",
    name: "Video Downloader",
    short: "Video",
    blurb:
      "Save from YouTube, Vimeo, X, Reddit, TikTok, and 1,000+ sites. Choose quality. No account.",
    tag: "No account",
    accent: "video",
  },
  {
    slug: "reader",
    href: "/reader",
    name: "Reader",
    short: "Reader",
    blurb:
      "Paste any article URL for a calm, distraction-free reading view — typography first, clutter gone.",
    tag: "No account",
    accent: "reader",
  },
  {
    slug: "prices",
    href: "/prices",
    name: "Price Tracker",
    short: "Prices",
    blurb:
      "Watch store prices and get a Telegram ping when they hit your target — not another inbox.",
    tag: "Telegram alerts",
    accent: "prices",
  },
] as const;
