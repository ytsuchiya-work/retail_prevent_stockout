"""Lakeflow Spark Declarative Pipeline — retail_prevent_stockout
Bronze (Auto Loader + CSV masters) -> Silver (enrich) -> Gold (fact / KPI / weekly).
Default catalog/schema is set in the pipeline settings:
  classic_stable_ytcy_catalog.retail_prevent_stockout
"""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

VOL = "/Volumes/classic_stable_ytcy_catalog/retail_prevent_stockout/raw"

# ---------------------------------------------------------------- BRONZE
@dp.table(name="bronze_sales", comment="POS 売上/在庫 生データ (Auto Loader, parquet)")
def bronze_sales():
    # parquet は自己記述的なので schemaHints は不要 (型ヒントを付けると int64↔int32 の
    # 不一致で全値が _rescued_data 送りになり null 化するため付けない)。
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .load(f"{VOL}/sales")
        # pandas datetime64 は timestamp_ntz と推論され Delta の追加機能を要求するため date にキャスト
        .withColumn("date", F.to_date("date"))
        .withColumn("_ingested_at", F.current_timestamp())
    )

@dp.materialized_view(name="bronze_store", comment="店舗マスタ")
def bronze_store():
    return (spark.read.format("csv").option("header", True).option("inferSchema", True)
            .load(f"{VOL}/store_master.csv"))

@dp.materialized_view(name="bronze_product", comment="商品(SKU)マスタ")
def bronze_product():
    return (spark.read.format("csv").option("header", True).option("inferSchema", True)
            .load(f"{VOL}/product_master.csv"))

@dp.materialized_view(name="bronze_weather", comment="地域×日次 気温")
def bronze_weather():
    return (spark.read.format("csv").option("header", True).option("inferSchema", True)
            .load(f"{VOL}/weather.csv")
            .withColumn("date", F.to_date("date")))

# ---------------------------------------------------------------- SILVER
@dp.materialized_view(
    name="silver_sales",
    comment="売上を商品/店舗/気温で enrich し、売上金額・欠品ロスを算出")
@dp.expect_or_drop("valid_units", "units_sold >= 0")
@dp.expect_or_drop("valid_demand", "true_demand >= 0")
def silver_sales():
    s = spark.read.table("bronze_sales").withColumn("date", F.to_date("date"))
    p = spark.read.table("bronze_product")
    st = spark.read.table("bronze_store")
    w = spark.read.table("bronze_weather")
    return (
        s.join(p, "sku_id", "left")
         .join(st, "store_id", "left")
         .join(w, ["region", "date"], "left")
         .withColumn("net_price", F.col("unit_price") * (1 - F.coalesce(F.col("discount_pct"), F.lit(0.0))))
         .withColumn("revenue", F.col("units_sold") * F.col("net_price"))
         .withColumn("lost_units", F.greatest(F.col("true_demand") - F.col("units_sold"), F.lit(0)))
         .withColumn("lost_revenue", F.col("lost_units") * F.col("net_price"))
         .withColumn("year", F.year("date"))
         .withColumn("month", F.month("date"))
         .withColumn("dow", F.dayofweek("date"))
         .withColumn("weekofyear", F.weekofyear("date"))
    )

# ---------------------------------------------------------------- GOLD
@dp.materialized_view(
    name="gold_daily_sales",
    comment="分析用ファクト: 店舗×SKU×日 (ビジネス次元を保持)",
    cluster_by=["date", "store_id"])
def gold_daily_sales():
    return spark.read.table("silver_sales").select(
        "date", "year", "month", "dow", "weekofyear",
        "store_id", "store_name", "region", "prefecture", "store_type",
        "sku_id", "product_name", "category", "style_id", "color", "size", "season",
        "units_sold", "true_demand", "lost_units", "on_hand_eod", "was_stockout",
        "promo_flag", "discount_pct", "unit_price", "unit_cost", "net_price",
        "revenue", "lost_revenue", "temp_avg",
    )

@dp.materialized_view(
    name="gold_daily_kpi",
    comment="日次KPIロールアップ (地域×カテゴリ): 売上・欠品ロス・欠品率")
def gold_daily_kpi():
    g = spark.read.table("gold_daily_sales")
    return (
        g.groupBy("date", "region", "category")
         .agg(
            F.sum("units_sold").alias("units_sold"),
            F.sum("true_demand").alias("true_demand"),
            F.sum("lost_units").alias("lost_units"),
            F.sum("revenue").alias("revenue"),
            F.sum("lost_revenue").alias("lost_revenue"),
            F.avg("was_stockout").alias("stockout_rate"),
            F.sum("on_hand_eod").alias("on_hand_units"),
         )
    )

@dp.materialized_view(
    name="gold_store_sku_weekly",
    comment="店舗×SKU×週 の集計 (Genie/需要予測の学習元)")
def gold_store_sku_weekly():
    g = spark.read.table("gold_daily_sales")
    return (
        g.withColumn("week_start", F.date_sub("date", F.expr("dayofweek(date) - 1")))
         .groupBy("week_start", "store_id", "store_type", "region",
                  "sku_id", "category", "style_id", "season")
         .agg(
            F.sum("units_sold").alias("units_sold"),
            F.sum("true_demand").alias("true_demand"),
            F.sum("lost_units").alias("lost_units"),
            F.sum("revenue").alias("revenue"),
            F.sum("lost_revenue").alias("lost_revenue"),
            F.avg("temp_avg").alias("temp_avg"),
            F.max("promo_flag").alias("had_promo"),
            F.avg("on_hand_eod").alias("avg_on_hand"),
            F.first("unit_price").alias("unit_price"),
            F.first("unit_cost").alias("unit_cost"),
         )
    )
