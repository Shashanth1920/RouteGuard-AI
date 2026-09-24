"""File: creates the FastAPI app, plus a static local-only UI at / for
manually poking the API and seeing route/tool/decision details without curl."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router

app = FastAPI(title="routeguard-ai")
app.include_router(router)
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
