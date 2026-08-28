#!/usr/bin/env python3
"""Load app-facing Delta exports (CSV in the UC Volume) into Lakebase (Autoscaling Postgres).

Run LOCALLY (needs the databricks CLI + psycopg2). Downloads the CSV exports written by
notebook 04, then creates the `retail` database + tables and bulk-inserts.

Usage: python scripts/load_lakebase.py --profile aigw-pat
"""
import argparse, csv, json, os, subprocess, tempfile, glob
import psycopg2
from psycopg2.extras import execute_values

PROJECT = "rps-retail"
ENDPOINT = f"projects/{PROJECT}/branches/production/endpoints/primary"
BRANCH = f"projects/{PROJECT}/branches/production"
VOL_EXPORT = "dbfs:/Volumes/classic_stable_ytcy_catalog/retail_prevent_stockout/raw/export"
DB = "retail"

# column -> postgres type (unknown columns default to TEXT)
TYPES = {
    "ml_wape": "double precision", "baseline_wape": "double precision",
    "wape_improvement_pct": "double precision",
    "annual_saved_lost_jpy": "bigint", "annual_saved_overstock_jpy": "bigint",
    "annual_saved_total_jpy": "bigint", "current_annual_lost_jpy": "bigint",
    "current_annual_overstock_jpy": "bigint", "eval_weeks": "int", "n_store_sku": "int",
    "unit_price": "int", "unit_cost": "int", "on_hand": "int", "target_stock": "int",
    "recommended_order_qty": "int", "potential_lost_rev": "bigint",
    "forecast_next_week": "double precision", "cover_ratio": "double precision",
    "true_demand": "double precision", "ml_forecast": "double precision",
    "coarse_forecast": "double precision", "temp_avg": "double precision",
    "had_promo": "int", "week_start": "date",
}
INT_COLS = {c for c, t in TYPES.items() if t in ("int", "bigint")}
FLOAT_COLS = {c for c, t in TYPES.items() if t == "double precision"}


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def coerce(col, val):
    if val is None or val == "":
        return None
    if col in INT_COLS:
        try: return int(float(val))
        except ValueError: return None
    if col in FLOAT_COLS:
        try: return float(val)
        except ValueError: return None
    return val


def load_table(cur, name, csv_path):
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames
        rows = [[coerce(c, r[c]) for c in cols] for r in reader]
    coldefs = ", ".join(f'"{c}" {TYPES.get(c, "text")}' for c in cols)
    cur.execute(f'DROP TABLE IF EXISTS "{name}"')
    cur.execute(f'CREATE TABLE "{name}" ({coldefs})')
    if rows:
        collist = ", ".join(f'"{c}"' for c in cols)
        execute_values(cur, f'INSERT INTO "{name}" ({collist}) VALUES %s', rows)
    print(f"  {name}: {len(rows)} rows, {len(cols)} cols")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="aigw-pat")
    ap.add_argument("--grant-sp", default="", help="App service principal client id to grant read access")
    args = ap.parse_args()
    P = ["--profile", args.profile]

    host = json.loads(sh("databricks", "postgres", "list-endpoints", BRANCH, *P, "-o", "json"))[0]["status"]["hosts"]["host"]
    token = json.loads(sh("databricks", "postgres", "generate-database-credential", ENDPOINT, *P, "-o", "json"))["token"]
    email = json.loads(sh("databricks", "current-user", "me", *P, "-o", "json"))["userName"]
    print("host:", host, "user:", email)

    # 1) ensure database exists (connect to default 'postgres' db first)
    conn = psycopg2.connect(host=host, port=5432, dbname="postgres", user=email, password=token, sslmode="require")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (DB,))
        if not cur.fetchone():
            cur.execute(f"CREATE DATABASE {DB}")
            print("created database", DB)
    conn.close()

    # 2) download CSV exports
    tmp = tempfile.mkdtemp(prefix="rps_export_")
    sh("databricks", "fs", "cp", "-r", VOL_EXPORT, tmp, *P)
    print("downloaded exports to", tmp)

    # 3) load each table
    conn = psycopg2.connect(host=host, port=5432, dbname=DB, user=email, password=token, sslmode="require")
    with conn:
        with conn.cursor() as cur:
            for name in ["value_summary", "recommendations", "reorder_reco", "forecast"]:
                parts = glob.glob(os.path.join(tmp, name, "*.csv"))
                if not parts:
                    print(f"  !! no csv for {name}"); continue
                load_table(cur, name, parts[0])
            # helpful indexes
            cur.execute('CREATE INDEX IF NOT EXISTS ix_reco_store ON recommendations(store_id)')
            cur.execute('CREATE INDEX IF NOT EXISTS ix_reco_cat ON recommendations(category)')
            cur.execute('CREATE INDEX IF NOT EXISTS ix_fc_region ON forecast(region)')
    conn.close()

    # grant read access to the app service principal (creates its Postgres role if missing)
    if args.grant_sp:
        sp = args.grant_sp
        conn = psycopg2.connect(host=host, port=5432, dbname=DB, user=email, password=token, sslmode="require")
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (sp,))
            if not cur.fetchone():
                cur.execute(f'CREATE ROLE "{sp}" LOGIN')
                print("created role", sp)
            cur.execute(f'GRANT CONNECT ON DATABASE {DB} TO "{sp}"')
            cur.execute(f'GRANT USAGE ON SCHEMA public TO "{sp}"')
            cur.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{sp}"')
            cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO "{sp}"')
        conn.close()
        print("granted read access to SP", sp)
    print("done.")


if __name__ == "__main__":
    main()
