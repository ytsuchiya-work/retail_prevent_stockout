# Databricks notebook source
# MAGIC %md
# MAGIC # 04. 生成AI (ai_query) で発注推奨の理由文を生成
# MAGIC
# MAGIC `reorder_reco` の優先度が高い店舗×SKU について、Foundation Model で
# MAGIC **発注アクションの根拠 (自然言語)** をバッチ生成し、`recommendations` テーブルに保存。
# MAGIC バッチ生成を採用する理由: コスト管理・一貫性・アプリ表示の低レイテンシ (事前計算)。

# COMMAND ----------

CATALOG, SCHEMA = "classic_stable_ytcy_catalog", "retail_prevent_stockout"
spark.sql(f"USE {CATALOG}.{SCHEMA}")
ENDPOINT = "databricks-meta-llama-3-1-8b-instruct"

# COMMAND ----------

# MAGIC %md ## 優先度上位を抽出し、ai_query で理由文をバッチ生成
# MAGIC 欠品リスク「高/中」または想定機会損失が大きい上位を対象 (コスト上限のため)。

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE recommendations AS
WITH ranked AS (
  SELECT *,
    row_number() OVER (ORDER BY (stockout_risk='高') DESC, potential_lost_rev DESC) AS rk
  FROM reorder_reco
),
top AS (SELECT * FROM ranked WHERE rk <= 300)
SELECT
  store_id, store_name, prefecture, region, sku_id, product_name, category, color, size,
  season, unit_price, on_hand, forecast_next_week, target_stock,
  recommended_order_qty, stockout_risk, potential_lost_rev,
  ai_query(
    '{ENDPOINT}',
    CONCAT(
      'あなたはアパレルチェーンの需要予測アシスタントです。以下の店舗×商品について、発注担当者向けに',
      '発注推奨の根拠を日本語で1〜2文、具体的な数値を交えて簡潔に述べてください。前置き・箇条書きは不要。\n',
      '店舗:', store_name, '(', prefecture, ') 商品:', product_name,
      ' カテゴリ:', category, ' 季節属性:', season, '\n',
      '現在庫:', CAST(on_hand AS STRING), '個 翌週予測需要:', CAST(round(forecast_next_week,1) AS STRING),
      '個 推奨発注:', CAST(recommended_order_qty AS STRING), '個 欠品リスク:', stockout_risk,
      ' 想定機会損失:', CAST(potential_lost_rev AS STRING), '円'
    )
  ) AS ai_reason
FROM top
""")
print("recommendations rows:", spark.table("recommendations").count())

# COMMAND ----------

display(spark.sql("SELECT store_name, product_name, on_hand, forecast_next_week, recommended_order_qty, stockout_risk, ai_reason FROM recommendations LIMIT 5"))

# COMMAND ----------

# MAGIC %md ## Lakebase 配信用に app テーブルを CSV エクスポート (単一ファイル)

# COMMAND ----------

VOL = f"/Volumes/{CATALOG}/{SCHEMA}/raw"
EXPORT = f"{VOL}/export"
def export_csv(table, name):
    (spark.table(table).coalesce(1).write.mode("overwrite")
        .option("header", True).option("escape", '"').csv(f"{EXPORT}/{name}"))
    print(name, spark.table(table).count(), "rows")

export_csv("value_summary", "value_summary")
export_csv("recommendations", "recommendations")
export_csv("reorder_reco", "reorder_reco")
export_csv("forecast", "forecast")
print("exported to", EXPORT)
