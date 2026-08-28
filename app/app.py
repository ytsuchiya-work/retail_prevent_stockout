"""Retail Stockout Prevention — Databricks App (FastAPI + React)."""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from server.db import pool
from server.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open(wait=True, timeout=30.0)
    yield
    pool.close()


app = FastAPI(title="Retail Stockout Prevention", lifespan=lifespan)
app.include_router(router, prefix="/api")

_frontend = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(_frontend):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        return FileResponse(os.path.join(_frontend, "index.html"))
