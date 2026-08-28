import { useEffect, useState } from "react";
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from "recharts";
import {
  TrendingUp, PackageSearch, LineChart as LineIcon, Sparkles, AlertTriangle,
} from "lucide-react";
import { api, Kpis, Reco, ForecastPoint } from "./api";

const JPY_PER_USD = 150;
const oku = (n: number) => (n / 1e8).toFixed(2) + "億円";
const man = (n: number) => Math.round(n / 1e4).toLocaleString() + "万円";
const usd = (n: number) => "$" + (n / JPY_PER_USD / 1e6).toFixed(2) + "M";
const pct = (n: number) => (n * 100).toFixed(1) + "%";

type Tab = "exec" | "reco" | "forecast" | "genie";

export default function App() {
  const [tab, setTab] = useState<Tab>("exec");
  return (
    <>
      <div className="header">
        <div className="header-inner">
          <span className="tag">DATABRICKS LAKEHOUSE + AI</span>
          <h1>在庫最適化コックピット</h1>
          <p>アパレルチェーンの需要予測 — 欠品による売上ロスと過剰発注を、店舗×SKU 粒度の AI 予測で削減</p>
        </div>
      </div>
      <div className="app">
        <div className="tabs">
          <button className={`tab ${tab === "exec" ? "active" : ""}`} onClick={() => setTab("exec")}>
            <TrendingUp size={16} /> エグゼクティブ・サマリー
          </button>
          <button className={`tab ${tab === "reco" ? "active" : ""}`} onClick={() => setTab("reco")}>
            <PackageSearch size={16} /> 発注推奨（店長/MD）
          </button>
          <button className={`tab ${tab === "forecast" ? "active" : ""}`} onClick={() => setTab("forecast")}>
            <LineIcon size={16} /> 需要予測の精度
          </button>
          <button className={`tab ${tab === "genie" ? "active" : ""}`} onClick={() => setTab("genie")}>
            <Sparkles size={16} /> Genie で質問
          </button>
        </div>
        {tab === "exec" && <Executive />}
        {tab === "reco" && <Recommendations />}
        {tab === "forecast" && <Forecast />}
        {tab === "genie" && <Genie />}
      </div>
    </>
  );
}

function Executive() {
  const [k, setK] = useState<Kpis | null>(null);
  useEffect(() => { api.kpis().then(setK).catch(console.error); }, []);
  if (!k) return <div className="loading">読み込み中…</div>;
  const v = k.value;
  const wapeData = [
    { name: "粗い予測\n(カテゴリ一律)", wape: +(v.baseline_wape * 100).toFixed(1), fill: "#98a6b4" },
    { name: "細粒度 ML\n(店舗×SKU)", wape: +(v.ml_wape * 100).toFixed(1), fill: "#ff3621" },
  ];
  const costData = [
    { name: "現状（粗い発注）", lost: Math.round(v.current_annual_lost_jpy / 1e4), over: Math.round(v.current_annual_overstock_jpy / 1e4) },
    {
      name: "AI 最適化後",
      lost: Math.round((v.current_annual_lost_jpy - v.annual_saved_lost_jpy) / 1e4),
      over: Math.round((v.current_annual_overstock_jpy - v.annual_saved_overstock_jpy) / 1e4),
    },
  ];
  return (
    <>
      <div className="section-title">ビジネス成果</div>
      <div className="section-sub">
        店舗×SKU 粒度の需要予測で、欠品による機会損失と過剰在庫コストを同時に削減します。
      </div>

      <div className="grid k4">
        <div className="card kpi">
          <div className="bar" />
          <div className="label">年間削減効果（合計）</div>
          <div className="value hero">{oku(v.annual_saved_total_jpy)}</div>
          <div className="foot">概算 ≈ {usd(v.annual_saved_total_jpy)} / 年（1USD=¥{JPY_PER_USD}換算）</div>
        </div>
        <div className="card kpi">
          <div className="bar g" />
          <div className="label">欠品ロス削減</div>
          <div className="value">{man(v.annual_saved_lost_jpy)}<span style={{ fontSize: 15 }}>/年</span></div>
          <div className="foot">売れたはずの需要を取りこぼさない</div>
        </div>
        <div className="card kpi">
          <div className="bar a" />
          <div className="label">過剰在庫コスト削減</div>
          <div className="value">{man(v.annual_saved_overstock_jpy)}<span style={{ fontSize: 15 }}>/年</span></div>
          <div className="foot">値引き処分・保管・評価損を圧縮</div>
        </div>
        <div className="card kpi">
          <div className="bar n" />
          <div className="label">予測精度の改善（WAPE）</div>
          <div className="value">{v.wape_improvement_pct}%<span style={{ fontSize: 15 }}> 改善</span></div>
          <div className="foot">{pct(v.baseline_wape)} → {pct(v.ml_wape)}</div>
        </div>
      </div>

      <div className="grid k2" style={{ marginTop: 16 }}>
        <div className="card">
          <h3>予測精度：粗い予測 vs 細粒度 ML</h3>
          <div className="sub">WAPE（加重絶対誤差率）— 低いほど高精度</div>
          <div className="chartbox">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={wapeData} margin={{ top: 10, right: 10, left: -10, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} interval={0} />
                <YAxis tick={{ fontSize: 12 }} unit="%" />
                <Tooltip formatter={(x) => `${x}%`} />
                <Bar dataKey="wape" radius={[6, 6, 0, 0]}>
                  {wapeData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <h3>年間コスト：現状 vs AI 最適化後</h3>
          <div className="sub">欠品ロス＋過剰在庫コスト（単位：万円/年）</div>
          <div className="chartbox">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={costData} margin={{ top: 10, right: 10, left: 0, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip formatter={(x: number) => `${x.toLocaleString()}万円`} />
                <Bar dataKey="lost" stackId="a" fill="#ff3621" name="欠品ロス" radius={[0, 0, 0, 0]} />
                <Bar dataKey="over" stackId="a" fill="#2272b4" name="過剰在庫" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="legend">
            <span><i className="dot" style={{ background: "#ff3621" }} />欠品ロス</span>
            <span><i className="dot" style={{ background: "#2272b4" }} />過剰在庫コスト</span>
          </div>
        </div>
      </div>

      <div className="grid k3" style={{ marginTop: 16 }}>
        <div className="card kpi">
          <div className="label">欠品リスク「高」の店舗×SKU</div>
          <div className="value" style={{ color: "var(--red)" }}>{Number(k.agg.high_risk_cnt).toLocaleString()}</div>
          <div className="foot">今すぐ発注アクションが必要</div>
        </div>
        <div className="card kpi">
          <div className="label">推奨発注数量（合計）</div>
          <div className="value">{Number(k.agg.total_reco_qty).toLocaleString()}<span style={{ fontSize: 15 }}> 点</span></div>
          <div className="foot">最新週の全店舗×SKU 合算</div>
        </div>
        <div className="card kpi">
          <div className="label">分析対象の店舗×SKU 数</div>
          <div className="value">{Number(k.agg.n_store_sku).toLocaleString()}</div>
          <div className="foot">評価期間 {v.eval_weeks} 週で効果を測定</div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>統合データフロー（生データ → 意思決定）</h3>
        <div className="flow">
          <span className="node">合成POS/在庫データ</span><span className="arrow">→</span>
          <span className="node">Lakeflow パイプライン</span><span className="arrow">→</span>
          <span className="node">Unity Catalog（統治）</span><span className="arrow">→</span>
          <span className="node">ML 需要予測＋生成AI</span><span className="arrow">→</span>
          <span className="node">Lakebase（OLTP配信）</span><span className="arrow">→</span>
          <span className="node">Genie＋本アプリ</span>
        </div>
        <p className="note" style={{ marginTop: 12 }}>
          ※ 金額は本デモの合成データに基づく概算です。評価期間（直近{v.eval_weeks}週）の在庫シミュレーションで、
          「粗い発注方針」と「ML 予測に基づく発注方針」を同一の真の需要に対して比較し、年換算しています。
        </p>
      </div>
    </>
  );
}

function riskBadge(r: string) {
  const cls = r === "高" ? "hi" : r === "中" ? "mid" : "lo";
  return <span className={`badge ${cls}`}>{r}</span>;
}

function Recommendations() {
  const [rows, setRows] = useState<Reco[]>([]);
  const [filters, setFilters] = useState<{ stores: any[]; categories: string[] }>({ stores: [], categories: [] });
  const [store, setStore] = useState("");
  const [category, setCategory] = useState("");
  const [risk, setRisk] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => { api.filters().then((f) => setFilters(f as any)).catch(console.error); }, []);
  useEffect(() => {
    setLoading(true);
    api.recommendations({ store, category, risk, limit: 150 })
      .then((d) => setRows(d.rows)).catch(console.error).finally(() => setLoading(false));
  }, [store, category, risk]);

  return (
    <>
      <div className="section-title">発注推奨リスト（店長 / マーチャンダイザー向け）</div>
      <div className="section-sub">
        翌週の予測需要・現在庫・欠品リスクに基づく発注推奨と、生成AIによる根拠。優先度（欠品リスク→機会損失）順。
      </div>
      <div className="toolbar">
        <select value={store} onChange={(e) => setStore(e.target.value)}>
          <option value="">全店舗</option>
          {filters.stores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
        </select>
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">全カテゴリ</option>
          {filters.categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={risk} onChange={(e) => setRisk(e.target.value)}>
          <option value="">全リスク</option>
          <option value="高">欠品リスク：高</option>
          <option value="中">欠品リスク：中</option>
          <option value="低">欠品リスク：低</option>
        </select>
        <span className="pill">{rows.length} 件表示</span>
      </div>
      {loading ? <div className="loading">読み込み中…</div> : (
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr>
                <th>店舗</th><th>商品</th><th>カテゴリ</th>
                <th className="num">現在庫</th><th className="num">翌週予測</th>
                <th className="num">推奨発注</th><th>欠品リスク</th>
                <th className="num">想定機会損失</th><th>AI 根拠</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td>{r.store_name}<div style={{ color: "var(--ink-soft)", fontSize: 11 }}>{r.prefecture}</div></td>
                  <td>{r.product_name}<div style={{ color: "var(--ink-soft)", fontSize: 11 }}>{r.color}・{r.size}</div></td>
                  <td>{r.category}</td>
                  <td className="num">{r.on_hand}</td>
                  <td className="num">{Number(r.forecast_next_week).toFixed(1)}</td>
                  <td className="num" style={{ fontWeight: 700 }}>{r.recommended_order_qty}</td>
                  <td>{riskBadge(r.stockout_risk)}</td>
                  <td className="num">{Number(r.potential_lost_rev).toLocaleString()}円</td>
                  <td className="reason">{r.ai_reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function Forecast() {
  const [rows, setRows] = useState<ForecastPoint[]>([]);
  const [filters, setFilters] = useState<{ regions: string[]; categories: string[] }>({ regions: [], categories: [] });
  const [region, setRegion] = useState("");
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => { api.filters().then((f) => setFilters(f as any)).catch(console.error); }, []);
  useEffect(() => {
    setLoading(true);
    api.forecast({ region, category })
      .then((d) => setRows(d.rows.map((r) => ({
        week_start: String(r.week_start).slice(0, 10),
        actual: Math.round(Number(r.actual)),
        ml: Math.round(Number(r.ml)),
        coarse: Math.round(Number(r.coarse)),
      })))).catch(console.error).finally(() => setLoading(false));
  }, [region, category]);

  return (
    <>
      <div className="section-title">需要予測の精度：細粒度 ML が「粒度不足」を解消</div>
      <div className="section-sub">
        評価期間の週次で、実需要（真の需要）に対する ML 予測と粗い予測（カテゴリ一律）を比較。
      </div>
      <div className="toolbar">
        <select value={region} onChange={(e) => setRegion(e.target.value)}>
          <option value="">全地域</option>
          {filters.regions.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">全カテゴリ</option>
          {filters.categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div className="card">
        {loading ? <div className="loading">読み込み中…</div> : (
          <>
            <div className="chartbox" style={{ height: 380 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rows} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="week_start" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(x: number) => `${x.toLocaleString()} 点`} />
                  <Line type="monotone" dataKey="actual" stroke="#1b3139" strokeWidth={3} dot={false} name="実需要" />
                  <Line type="monotone" dataKey="ml" stroke="#ff3621" strokeWidth={2.5} dot={false} name="ML 予測" />
                  <Line type="monotone" dataKey="coarse" stroke="#98a6b4" strokeWidth={2} strokeDasharray="5 4" dot={false} name="粗い予測" />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="legend">
              <span><i className="dot" style={{ background: "#1b3139" }} />実需要</span>
              <span><i className="dot" style={{ background: "#ff3621" }} />ML 予測（店舗×SKU）</span>
              <span><i className="dot" style={{ background: "#98a6b4" }} />粗い予測（カテゴリ一律）</span>
            </div>
          </>
        )}
      </div>
    </>
  );
}

function Genie() {
  const [q, setQ] = useState("");
  const [ans, setAns] = useState<{ answer: string; sql: string | null } | null>(null);
  const [link, setLink] = useState<{ url: string; space_id: string } | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => { api.genieLink().then(setLink).catch(console.error); }, []);
  const ask = async () => {
    if (!q.trim()) return;
    setLoading(true); setAns(null);
    try { setAns(await api.genieAsk(q)); } catch (e: any) { setAns({ answer: String(e), sql: null }); }
    setLoading(false);
  };
  const samples = ["先週最も欠品した店舗はどこ？", "推奨発注額が最大のSKUトップ5", "アウターの地域別売上"];
  return (
    <>
      <div className="section-title">Genie でデータに自然言語で質問</div>
      <div className="section-sub">
        ビジネスユーザーが SQL を書かずに、統治されたデータへセルフサービスで問い合わせ。
      </div>
      <div className="card">
        <div className="genie-input">
          <input placeholder="例：先週最も欠品した店舗は？" value={q}
            onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask()} />
          <button className="btn" onClick={ask}>質問する</button>
        </div>
        <div className="toolbar">
          {samples.map((s) => <span key={s} className="pill" style={{ cursor: "pointer" }} onClick={() => setQ(s)}>{s}</span>)}
        </div>
        {loading && <div className="loading">Genie が回答中…</div>}
        {ans && (
          <div className="answer">
            <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
              <Sparkles size={18} color="#ff3621" />
              <div style={{ whiteSpace: "pre-wrap" }}>{ans.answer}</div>
            </div>
            {ans.sql && <pre>{ans.sql}</pre>}
          </div>
        )}
        {link?.url && (
          <p className="note" style={{ marginTop: 14 }}>
            <AlertTriangle size={13} style={{ verticalAlign: "-2px" }} /> フル機能の Genie ルーム：{" "}
            <a href={link.url} target="_blank" rel="noreferrer">Databricks で開く</a>
          </p>
        )}
      </div>
    </>
  );
}
