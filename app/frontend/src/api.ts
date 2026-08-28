export interface ValueSummary {
  ml_wape: number;
  baseline_wape: number;
  wape_improvement_pct: number;
  annual_saved_lost_jpy: number;
  annual_saved_overstock_jpy: number;
  annual_saved_total_jpy: number;
  current_annual_lost_jpy: number;
  current_annual_overstock_jpy: number;
  eval_weeks: number;
  n_store_sku: number;
}

export interface Kpis {
  value: ValueSummary;
  agg: {
    n_store_sku: number;
    high_risk_cnt: number;
    mid_risk_cnt: number;
    total_reco_qty: number;
    total_potential_lost: number;
  };
}

export interface Reco {
  store_id: string;
  store_name: string;
  prefecture: string;
  sku_id: string;
  product_name: string;
  category: string;
  color: string;
  size: string;
  season: string;
  unit_price: number;
  on_hand: number;
  forecast_next_week: number;
  target_stock: number;
  recommended_order_qty: number;
  stockout_risk: string;
  potential_lost_rev: number;
  ai_reason: string;
}

export interface ForecastPoint {
  week_start: string;
  actual: number;
  ml: number;
  coarse: number;
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}

export const api = {
  kpis: () => get<Kpis>("/api/kpis"),
  filters: () =>
    get<{ stores: { store_id: string; store_name: string; region: string }[]; categories: string[]; regions: string[] }>(
      "/api/filters"
    ),
  recommendations: (p: { store?: string; category?: string; risk?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (p.store) q.set("store", p.store);
    if (p.category) q.set("category", p.category);
    if (p.risk) q.set("risk", p.risk);
    q.set("limit", String(p.limit ?? 100));
    return get<{ rows: Reco[] }>(`/api/recommendations?${q}`);
  },
  forecast: (p: { region?: string; category?: string }) => {
    const q = new URLSearchParams();
    if (p.region) q.set("region", p.region);
    if (p.category) q.set("category", p.category);
    return get<{ rows: ForecastPoint[] }>(`/api/forecast?${q}`);
  },
  genieLink: () => get<{ space_id: string; url: string }>("/api/genie/link"),
  genieAsk: async (question: string) => {
    const r = await fetch("/api/genie/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    return r.json() as Promise<{ answer: string; sql: string | null }>;
  },
};
