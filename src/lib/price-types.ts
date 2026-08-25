export type TrackedProduct = {
  id: string;
  url: string;
  name: string;
  currentPrice: number | null;
  targetPrice: number;
  currency: string;
  username: string;
  lastChecked: string | null;
  notified: boolean;
  createdAt: string;
  priceHistory: { at: string; price: number }[];
  errorCount: number;
  lastError: string;
};

export type PriceUser = {
  username: string;
  createdAt: string;
  isAdmin: boolean;
};
