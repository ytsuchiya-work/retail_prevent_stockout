# retail_prevent_stockout

アパレルチェーンの需要予測の粒度不足による売上ロスと過剰発注を、AIを活用して改善するデモです。

**課題**: 「店舗 × SKU × 日」の細かい粒度で需要を予測できず、カテゴリ一律の粗い予測に依存すると、
人気サイズ/色の**欠品による売上ロス**と、需要の低い店舗への**過剰発注（値引き処分・在庫評価損・保管コスト）**
が同時に発生します。

**解決**: Databricks 上でエンドツーエンドに、細粒度の需要予測と生成AIによる発注アクション推奨を実装。
店長/MD は「今日どの SKU を何個発注すべきか」をアプリで即確認、経営層は KPI インパクトを把握できます。

## エンドツーエンドの統合データフロー

```
合成POS/在庫データ (UC Volume)
  └─▶ Lakeflow 宣言的パイプライン  (bronze → silver → gold / medallion)
        └─▶ Unity Catalog で統治     (classic_stable_ytcy_catalog.retail_prevent_stockout)
              └─▶ ML 需要予測 (店舗×SKU 週次, HistGBM) + 生成AI (ai_query で発注根拠文)
                    └─▶ Lakebase (Autoscaling Postgres) に配信テーブルを格納 (低レイテンシ OLTP)
                          └─▶ Genie ルーム (自然言語Q&A) + ビジネスアプリ (React + FastAPI)
```

## アセット構成

| パス | 内容 |
|------|------|
| `notebooks/01_generate_synthetic_data.py` | 合成POS/在庫/マスタ/気温/プロモを UC Volume に生成 |
| `pipelines/retail_pipeline.py` | Lakeflow 宣言的パイプライン (Auto Loader → medallion) |
| `notebooks/03_train_forecast.py` | 需要予測モデル学習・粗い予測との精度比較・在庫シミュレーションで効果を定量化・UC登録 |
| `notebooks/04_generate_recommendations.py` | `ai_query` で発注推奨の根拠文をバッチ生成、Lakebase 配信用CSVエクスポート |
| `scripts/load_lakebase.py` | 配信テーブルを Lakebase (Postgres) にロード (ローカル実行) |
| `app/` | ビジネスアプリ (React + FastAPI, Databricks App) |
| `databricks.yml`, `resources/` | Databricks Asset Bundle (パイプライン/ジョブ) |

## データモデル (gold 層)

- `gold_daily_sales` — 店舗×SKU×日 のファクト（実売・真の需要・欠品ロス・在庫・気温・プロモ）
- `gold_daily_kpi` — 地域×カテゴリ×日 の KPI ロールアップ
- `gold_store_sku_weekly` — 店舗×SKU×週 の集計（ML 学習元 / Genie）
- `forecast` / `reorder_reco` / `recommendations` / `value_summary` — 予測結果・発注推奨・効果サマリ

## デプロイ手順

```bash
PROFILE=fevm-classic-stable-ytcy   # または aigw-pat

# 1) データ生成（Volume へ）
databricks jobs submit --json '{"run_name":"gen","tasks":[{"task_key":"g","notebook_task":{"notebook_path":".../01_generate_synthetic_data"}}]}' -p $PROFILE

# 2) Lakeflow パイプライン（bundle でデプロイ）
databricks bundle deploy -t dev -p $PROFILE
databricks bundle run retail_pipeline -t dev -p $PROFILE

# 3) 学習 → 4) 推奨生成（notebook をジョブ実行）
# 5) Lakebase 作成 + ロード
databricks postgres create-project rps-retail --json '{"spec":{"display_name":"Retail Prevent Stockout"}}' -p $PROFILE
python scripts/load_lakebase.py --profile $PROFILE

# 6) アプリのフロントエンドをビルドしてデプロイ
cd app/frontend && npm install && npm run build && cd ..
databricks apps create retail-stockout -p $PROFILE
databricks sync app /Workspace/Users/<you>/retail-stockout --exclude node_modules --exclude .venv -p $PROFILE
databricks apps deploy retail-stockout --source-code-path /Workspace/Users/<you>/retail-stockout -p $PROFILE
# UI で「Database」(Lakebase) と「Model serving endpoint」リソースを付与して再デプロイ
```

## 意思決定とトレードオフ

- **細粒度(店舗×SKU) vs 粗い(カテゴリ一律)予測**: ロングテール需要の取りこぼしを解消。計算コストは serverless で吸収。
- **決定木系 GBM vs 深層学習/Prophet**: 説明可能性・学習コスト・serverless 適合性から HistGradientBoosting を採用。
- **Lakebase(OLTP) vs Warehouse 直読**: アプリのリアルタイム性を Lakebase が担い、分析系は Warehouse/Genie が担当。
- **ai_query バッチ生成 vs リアルタイム LLM 呼び出し**: コスト管理・一貫性・低レイテンシ表示のためバッチ事前生成。
- **Genie vs 固定ダッシュボード**: ビジネスユーザーのセルフサービス探索を可能にする。

> 金額・精度指標は本デモの合成データに基づく概算です。評価期間の在庫シミュレーションで
> 「粗い発注方針」と「ML 予測に基づく発注方針」を同一の真の需要に対して比較し、年換算しています。
