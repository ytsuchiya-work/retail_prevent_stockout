"""API routes — all business data served from Lakebase (Postgres) for low latency."""
import os
from fastapi import APIRouter, Query
from .db import query
from .config import get_workspace_client, get_workspace_host

router = APIRouter()


@router.get("/kpis")
def kpis():
    vs = query("SELECT * FROM value_summary LIMIT 1")
    agg = query("""
        SELECT
          COUNT(*)                                             AS n_store_sku,
          SUM(CASE WHEN stockout_risk='高' THEN 1 ELSE 0 END)  AS high_risk_cnt,
          SUM(CASE WHEN stockout_risk='中' THEN 1 ELSE 0 END)  AS mid_risk_cnt,
          SUM(recommended_order_qty)                           AS total_reco_qty,
          SUM(potential_lost_rev)                              AS total_potential_lost
        FROM reorder_reco
    """)
    return {"value": vs[0] if vs else {}, "agg": agg[0] if agg else {}}


@router.get("/filters")
def filters():
    stores = query("SELECT DISTINCT store_id, store_name, region FROM reorder_reco ORDER BY store_id")
    cats = query("SELECT DISTINCT category FROM reorder_reco ORDER BY category")
    regions = query("SELECT DISTINCT region FROM reorder_reco ORDER BY region")
    return {"stores": stores, "categories": [c["category"] for c in cats],
            "regions": [r["region"] for r in regions]}


@router.get("/recommendations")
def recommendations(store: str = Query(""), category: str = Query(""),
                    risk: str = Query(""), limit: int = Query(100)):
    where, params = [], []
    if store:
        where.append("store_id = %s"); params.append(store)
    if category:
        where.append("category = %s"); params.append(category)
    if risk:
        where.append("stockout_risk = %s"); params.append(risk)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    params.append(limit)
    rows = query(f"""
        SELECT store_id, store_name, prefecture, sku_id, product_name, category, color, size,
               season, unit_price, on_hand, forecast_next_week, target_stock,
               recommended_order_qty, stockout_risk, potential_lost_rev, ai_reason
        FROM recommendations {clause}
        ORDER BY (stockout_risk='高') DESC, potential_lost_rev DESC
        LIMIT %s
    """, params)
    return {"rows": rows}


@router.get("/forecast")
def forecast(region: str = Query(""), category: str = Query("")):
    where, params = [], []
    if region:
        where.append("region = %s"); params.append(region)
    if category:
        where.append("category = %s"); params.append(category)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = query(f"""
        SELECT week_start,
               SUM(true_demand)     AS actual,
               SUM(ml_forecast)     AS ml,
               SUM(coarse_forecast) AS coarse
        FROM forecast {clause}
        GROUP BY week_start ORDER BY week_start
    """, params)
    return {"rows": rows}


@router.post("/genie/ask")
def genie_ask(body: dict):
    space_id = os.environ.get("GENIE_SPACE_ID", "")
    q = (body or {}).get("question", "").strip()
    if not space_id:
        return {"answer": "Genie スペース未設定です。GENIE_SPACE_ID を設定してください。", "sql": None}
    if not q:
        return {"answer": "質問を入力してください。", "sql": None}
    try:
        w = get_workspace_client()
        res = w.genie.start_conversation_and_wait(space_id, q)
        text, sql = None, None
        for att in (res.attachments or []):
            if getattr(att, "text", None):
                text = att.text.content
            if getattr(att, "query", None):
                sql = att.query.query
        return {"answer": text or "(回答テキストなし)", "sql": sql}
    except Exception as e:  # noqa
        return {"answer": f"Genie 呼び出しエラー: {e}", "sql": None}


@router.get("/genie/link")
def genie_link():
    space_id = os.environ.get("GENIE_SPACE_ID", "")
    host = get_workspace_host()
    return {"space_id": space_id,
            "url": f"{host}/genie/rooms/{space_id}" if space_id else ""}
