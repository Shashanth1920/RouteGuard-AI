"""File: creates the FastAPI app, plus a static local-only UI at / for
manually poking the API and seeing route/tool/decision details without curl."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.db.logging import init_db

app = FastAPI(title="routeguard-ai")
app.include_router(router)
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")

try:
    init_db()
except Exception as e:
    # Logging fails open even at startup - a database that isn't ready yet
    # shouldn't stop the app from serving requests (they just won't be
    # logged until it is; save_request() warns on every request too).
    print(f"[routeguard] WARNING: could not initialize the database at startup: {e}")
