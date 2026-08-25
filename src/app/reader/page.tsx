import type { Metadata } from "next";
import { ReaderTool } from "@/components/tools/reader-tool";

export const metadata: Metadata = {
  title: "Reader",
  description:
    "Paste an article URL for a calm, distraction-free reading view — typography first, clutter gone.",
};

export default function ReaderPage() {
  return <ReaderTool />;
}
