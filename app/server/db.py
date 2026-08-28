"""Lakebase (Autoscaling Postgres) connection pool with per-connection OAuth token."""
import os
import psycopg
from psycopg_pool import ConnectionPool
from .config import get_workspace_client

_w = get_workspace_client()
ENDPOINT_NAME = os.environ["ENDPOINT_NAME"]


class OAuthConnection(psycopg.Connection):
    """Fresh OAuth token per new/recycled connection (no background refresh needed)."""
    @classmethod
    def connect(cls, conninfo="", **kwargs):
        cred = _w.postgres.generate_database_credential(endpoint=ENDPOINT_NAME)
        kwargs["password"] = cred.token
        return super().connect(conninfo, **kwargs)


def _conninfo() -> str:
    # In the app runtime PGUSER/PGHOST are auto-injected by the Database resource.
    # Locally, fall back to the current user's email + endpoint host env.
    host = os.environ["PGHOST"]
    port = os.environ.get("PGPORT", "5432")
    database = os.environ.get("PGDATABASE", "retail")
    user = os.environ.get("PGUSER")
    if not user:
        user = get_workspace_client().current_user.me().user_name
    sslmode = os.environ.get("PGSSLMODE", "require")
    return f"dbname={database} user={user} host={host} port={port} sslmode={sslmode}"


pool = ConnectionPool(
    conninfo=_conninfo(),
    connection_class=OAuthConnection,
    min_size=1,
    max_size=8,
    max_lifetime=2700,  # recycle before 1-hour OAuth token expiry
    open=False,
)


def query(sql: str, params=None):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
