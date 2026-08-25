import type { Metadata } from "next";
import { PriceTrackerTool } from "@/components/tools/price-tracker";

export const metadata: Metadata = {
  title: "Price Tracker",
  description:
    "Monitor product prices and get Telegram alerts when they hit your target.",
};

export default function PricesPage() {
  return <PriceTrackerTool />;
}
