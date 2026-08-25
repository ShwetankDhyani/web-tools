import type { Metadata } from "next";
import { VideoDownloaderTool } from "@/components/tools/video-downloader";

export const metadata: Metadata = {
  title: "Video Downloader",
  description:
    "Download videos from YouTube, Vimeo, X, Reddit, TikTok, and 1,000+ sites. Choose quality, then save.",
};

export default function VideoPage() {
  return <VideoDownloaderTool />;
}
