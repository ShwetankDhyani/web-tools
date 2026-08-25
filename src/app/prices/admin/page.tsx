import type { Metadata } from "next";
import { PriceAdmin } from "@/components/tools/price-admin";

export const metadata: Metadata = {
  title: "Price Tracker Admin",
  robots: { index: false, follow: false },
};

export default function PriceAdminPage() {
  return <PriceAdmin />;
}
