# Databricks notebook source
# MAGIC %md
# MAGIC # 01. 合成データ生成 (アパレルチェーン POS / 在庫)
# MAGIC
# MAGIC アパレルチェーンの「店舗 × SKU × 日」粒度の合成データを生成し、UC Volume に
# MAGIC ランディングファイル (parquet/csv) として書き出す。後続の Lakeflow パイプラインが取り込む。
# MAGIC
# MAGIC **需要予測デモの肝**: 「真の需要 (true_demand)」を潜在変数として生成し、在庫制約でクリップした
# MAGIC 「実売数 (units_sold)」と分離する。差分 = 欠品による機会損失 (lost_sales)。
# MAGIC 店舗×SKU の相互作用 (都心店はアウター、モール店はワンピが強い等) を仕込み、
# MAGIC 「カテゴリ一律の粗い予測」では取りこぼす細粒度シグナルを埋め込む。

# COMMAND ----------

import numpy as np
import pandas as pd

CATALOG = "classic_stable_ytcy_catalog"
SCHEMA = "retail_prevent_stockout"
VOL = f"/Volumes/{CATALOG}/{SCHEMA}/raw"

rng = np.random.default_rng(42)

# 期間: 直近2年 (日次)
DATES = pd.date_range("2024-08-26", "2026-08-24", freq="D")
N_DAYS = len(DATES)
print(f"days={N_DAYS}, {DATES.min().date()} .. {DATES.max().date()}")

# COMMAND ----------

# MAGIC %md ## 店舗マスタ

# COMMAND ----------

store_types = ["urban", "suburban", "mall"]
regions = {
    "関東": ["東京", "神奈川", "埼玉"],
    "関西": ["大阪", "京都", "兵庫"],
    "中部": ["愛知", "静岡"],
    "九州": ["福岡", "熊本"],
}
region_list = list(regions.keys())

stores = []
sid = 0
store_names = ["新宿", "渋谷", "横浜", "大宮", "梅田", "心斎橋", "京都河原町", "神戸三宮",
               "名古屋栄", "静岡", "博多", "熊本", "町田", "越谷イオン", "ららぽーと豊洲"]
for i, name in enumerate(store_names):
    region = region_list[i % len(region_list)]
    pref = regions[region][i % len(regions[region])]
    stype = store_types[i % 3]
    stores.append({
        "store_id": f"S{sid:03d}",
        "store_name": f"{name}店",
        "region": region,
        "prefecture": pref,
        "store_type": stype,
        "size_sqm": int(rng.integers(300, 1200)),
        "open_year": int(rng.integers(2005, 2022)),
    })
    sid += 1
store_df = pd.DataFrame(stores)
N_STORES = len(store_df)
print(N_STORES)
store_df.head()

# COMMAND ----------

# MAGIC %md ## 商品マスタ (SKU)

# COMMAND ----------

# カテゴリ: 季節性/気温感応/単価が異なる
categories = {
    "アウター":   {"season": "winter", "temp_sens": -1.0, "price": (12000, 35000), "base": 2.5},
    "トップス":   {"season": "all",    "temp_sens":  0.2, "price": (3000, 9000),   "base": 8.0},
    "ボトムス":   {"season": "all",    "temp_sens": -0.2, "price": (5000, 14000),  "base": 5.0},
    "ワンピース": {"season": "summer", "temp_sens":  0.8, "price": (7000, 18000),  "base": 3.5},
    "ニット":     {"season": "winter", "temp_sens": -0.9, "price": (6000, 16000),  "base": 4.0},
    "シャツ":     {"season": "spring", "temp_sens":  0.3, "price": (4000, 11000),  "base": 5.5},
    "スカート":   {"season": "summer", "temp_sens":  0.5, "price": (5000, 13000),  "base": 3.0},
    "アクセサリ": {"season": "all",    "temp_sens":  0.0, "price": (2000, 8000),   "base": 6.0},
}
colors = ["ブラック", "ホワイト", "ネイビー", "ベージュ", "グレー", "レッド", "グリーン"]
sizes = ["XS", "S", "M", "L", "XL"]

products = []
kid = 0
for cat, meta in categories.items():
    n_style = rng.integers(4, 7)  # スタイル数/カテゴリ
    for st in range(n_style):
        style_pop = rng.uniform(0.4, 1.6)  # スタイル人気度
        base_price = int(rng.uniform(*meta["price"]) // 100 * 100)
        for color in rng.choice(colors, size=int(rng.integers(2, 4)), replace=False):
            for size in sizes:
                # サイズ別人気 (M/L が中心)
                size_pop = {"XS": 0.5, "S": 0.9, "M": 1.3, "L": 1.1, "XL": 0.6}[size]
                products.append({
                    "sku_id": f"K{kid:04d}",
                    "product_name": f"{cat}_{st:02d}_{color}_{size}",
                    "category": cat,
                    "style_id": f"{cat}_{st:02d}",
                    "color": color,
                    "size": size,
                    "season": meta["season"],
                    "temp_sens": meta["temp_sens"],
                    "unit_price": base_price,
                    "unit_cost": int(base_price * rng.uniform(0.42, 0.55)),
                    "_style_pop": style_pop,
                    "_size_pop": size_pop,
                    "_cat_base": meta["base"],
                })
                kid += 1
product_df = pd.DataFrame(products)
N_SKU = len(product_df)
print(f"SKU={N_SKU}, styles={product_df.style_id.nunique()}")
product_df.head()

# COMMAND ----------

# MAGIC %md ## 気温 (地域×日次) — 季節性の駆動因子

# COMMAND ----------

doy = DATES.dayofyear.values
# 年周期: 最寒 1月, 最暑 8月
season_temp = 16 - 11 * np.cos(2 * np.pi * (doy - 20) / 365.25)
weather = []
region_offset = {"関東": 0, "関西": 1.0, "中部": -0.5, "九州": 2.5}
for region in region_list:
    noise = rng.normal(0, 2.5, N_DAYS)
    temp = season_temp + region_offset[region] + noise
    for d, t in zip(DATES, temp):
        weather.append({"date": d, "region": region, "temp_avg": round(float(t), 1)})
weather_df = pd.DataFrame(weather)
print(weather_df.shape)
weather_df.head()

# COMMAND ----------

# MAGIC %md ## プロモーション

# COMMAND ----------

# 週次でランダムに一部カテゴリをセール (割引率)
promos = []
pid = 0
d = DATES.min()
while d <= DATES.max():
    if rng.random() < 0.35:  # その週にプロモがある確率
        cat = rng.choice(list(categories.keys()))
        disc = float(rng.choice([0.1, 0.2, 0.3]))
        promos.append({
            "promo_id": f"P{pid:04d}", "category": cat,
            "start_date": d, "end_date": d + pd.Timedelta(days=6),
            "discount_pct": disc,
        })
        pid += 1
    d += pd.Timedelta(days=7)
promo_df = pd.DataFrame(promos)
# 日付×カテゴリ -> 割引率 のルックアップ
promo_lookup = {}
for _, r in promo_df.iterrows():
    for dd in pd.date_range(r.start_date, r.end_date):
        promo_lookup[(dd, r.category)] = r.discount_pct
print(f"promos={len(promo_df)}")

# COMMAND ----------

# MAGIC %md ## 需要生成 (true_demand) → 在庫制約 → 実売 (units_sold)
# MAGIC 店舗×カテゴリの親和性 (affinity) を仕込む。これが「粗い予測」では捉えられない細粒度シグナル。

# COMMAND ----------

# 店舗タイプ × カテゴリ の親和性行列 (細粒度シグナルの源泉)
affinity = {
    "urban":    {"アウター": 1.5, "ニット": 1.4, "シャツ": 1.3, "アクセサリ": 1.2,
                 "トップス": 1.0, "ボトムス": 1.0, "ワンピース": 0.7, "スカート": 0.7},
    "suburban": {"アウター": 0.9, "ニット": 1.0, "シャツ": 1.0, "アクセサリ": 0.9,
                 "トップス": 1.1, "ボトムス": 1.2, "ワンピース": 1.0, "スカート": 1.0},
    "mall":     {"アウター": 0.8, "ニット": 0.9, "シャツ": 0.9, "アクセサリ": 1.3,
                 "トップス": 1.2, "ボトムス": 1.1, "ワンピース": 1.6, "スカート": 1.5},
}
store_scale = {r.store_id: rng.uniform(0.7, 1.5) for _, r in store_df.iterrows()}
store_type_map = dict(zip(store_df.store_id, store_df.store_type))
store_region_map = dict(zip(store_df.store_id, store_df.region))

# 気温ルックアップ (region,date)->temp
temp_lookup = {(r.region, r.date): r.temp_avg for _, r in weather_df.iterrows()}

# 曜日係数 (週末が高い)
dow_factor = np.array([0.9, 0.85, 0.9, 0.95, 1.2, 1.6, 1.4])  # Mon..Sun

# COMMAND ----------

# メモリ節約のため店舗ごとにループし parquet を書き出す
import os
os.makedirs(f"{VOL}/sales", exist_ok=True)
os.makedirs(f"{VOL}/inventory", exist_ok=True)

date_arr = DATES.values
dow = DATES.dayofweek.values
year_frac = (doy / 365.25)

sku_meta = product_df.set_index("sku_id")
cat_arr = product_df["category"].values
season_arr = product_df["season"].values
tempsens_arr = product_df["temp_sens"].values
price_arr = product_df["unit_price"].values
stylepop_arr = product_df["_style_pop"].values
sizepop_arr = product_df["_size_pop"].values
catbase_arr = product_df["_cat_base"].values
sku_ids = product_df["sku_id"].values

# 季節性関数: season -> 日別係数 (0.5..1.6)
def season_curve(season, doy):
    if season == "winter":
        return 1.05 - 0.55 * np.cos(2 * np.pi * (doy - 15) / 365.25)   # 冬ピーク
    if season == "summer":
        return 1.05 + 0.55 * np.cos(2 * np.pi * (doy - 15) / 365.25)   # 夏ピーク
    if season == "spring":
        return 1.0 + 0.4 * np.sin(2 * np.pi * (doy - 60) / 365.25)
    return np.ones_like(doy, dtype=float)  # all

# 各SKUの季節カーブを事前計算
season_mat = np.vstack([season_curve(s, doy) for s in season_arr])  # (N_SKU, N_DAYS)

total_rows = 0
for _, srow in store_df.iterrows():
    sid = srow.store_id
    stype = srow.store_type
    region = srow.region
    sscale = store_scale[sid]
    temps = np.array([temp_lookup[(region, d)] for d in DATES])  # (N_DAYS,)

    sales_records = []
    inv_records = []
    for j in range(N_SKU):
        cat = cat_arr[j]
        aff = affinity[stype][cat]
        base = catbase_arr[j] * stylepop_arr[j] * sizepop_arr[j] * aff * sscale
        # 需要トレンド (ゆるやかな成長 + SKUごとのライフサイクル)
        trend = np.linspace(rng.uniform(0.8, 1.0), rng.uniform(1.0, 1.3), N_DAYS)
        seas = season_mat[j]
        # 気温感応 (temp_sens<0: 寒いほど需要増)
        temp_norm = (temps - temps.mean()) / (temps.std() + 1e-6)
        temp_effect = np.exp(tempsens_arr[j] * temp_norm * 0.25)
        dowf = dow_factor[dow]
        # プロモ
        promo_disc = np.array([promo_lookup.get((d, cat), 0.0) for d in DATES])
        promo_lift = 1.0 + promo_disc * 3.0  # 30%引きで+90%
        lam = base * trend * seas * temp_effect * dowf * promo_lift
        lam = np.clip(lam, 0.01, None)
        true_demand = rng.poisson(lam)

        # ---- 在庫シミュレーション: 「粗い」補充方針 (現状) ----
        # SKUの全国平均人気(スタイル/サイズ)と店舗規模は把握するが、
        # 「店舗×カテゴリ親和性・季節性・曜日・プロモ」を取りこぼす = 粒度不足。
        # 週1回(月)補充、10日カバー + 軽い安全在庫 → 需要スパイク(週末/季節/プロモ/親和性)で欠品。
        coarse_daily = catbase_arr[j] * stylepop_arr[j] * sizepop_arr[j] * sscale  # affinity/季節/曜日/promoを無視
        target = int(round(coarse_daily * 10)) + 2
        on_hand = np.zeros(N_DAYS, dtype=int)
        units_sold = np.zeros(N_DAYS, dtype=int)
        stock = target
        for t in range(N_DAYS):
            if dow[t] == 0:  # 月曜に目標まで補充
                stock = max(stock, target)
            sell = min(true_demand[t], stock)
            units_sold[t] = sell
            stock -= sell
            on_hand[t] = stock
        for t in range(N_DAYS):
            sales_records.append((
                DATES[t], sid, sku_ids[j], int(units_sold[t]), int(true_demand[t]),
                float(promo_disc[t]), 1 if promo_disc[t] > 0 else 0,
                int(on_hand[t]), 1 if (true_demand[t] > units_sold[t]) else 0,
            ))
        total_rows += N_DAYS

    sdf = pd.DataFrame(sales_records, columns=[
        "date", "store_id", "sku_id", "units_sold", "true_demand",
        "discount_pct", "promo_flag", "on_hand_eod", "was_stockout"])
    sdf.to_parquet(f"{VOL}/sales/{sid}.parquet", index=False)
    print(f"{sid}: {len(sdf):,} rows written")

print(f"TOTAL sales rows = {total_rows:,}")

# COMMAND ----------

# MAGIC %md ## マスタ / 気温 / プロモを CSV で書き出し

# COMMAND ----------

store_df.to_csv(f"{VOL}/store_master.csv", index=False)
product_df.drop(columns=["_style_pop", "_size_pop", "_cat_base"]).to_csv(
    f"{VOL}/product_master.csv", index=False)
weather_df.to_csv(f"{VOL}/weather.csv", index=False)
if len(promo_df):
    promo_df.to_csv(f"{VOL}/promotions.csv", index=False)
print("masters written")
print(dbutils.fs.ls(f"{VOL}"))
print(dbutils.fs.ls(f"{VOL}/sales")[:3])
