"""File: creates the FastAPI app. Nothing else lives here."""
from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="routeguard-ai")
app.include_router(router)
