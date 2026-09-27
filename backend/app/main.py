"""Handoff backend application entrypoint.

Creates the FastAPI app and wires up routes plus the extraction-error handler.

Loads ``backend/.env`` into the process environment at startup (if present) so
local development can supply Gemini settings via a .env file. Real shell/server
environment variables take precedence (``override=False``), so deployed
environments that set the vars directly are unaffected. Config is still read
from ``os.environ`` by ``load_gemini_config`` — this only populates it.
"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

# Load backend/.env (this file lives at backend/app/main.py, so the .env is one
# directory up). Loaded before the app/config is used; does not override vars
# already present in the environment.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

from app.api import analyze, clarification, health
from app.api.errors import register_error_handlers

app = FastAPI(title="Handoff")

# All API routes live under the /api prefix so the frontend can proxy /api.
app.include_router(health.router, prefix="/api")
app.include_router(analyze.router, prefix="/api")
app.include_router(clarification.router, prefix="/api")

# Translate typed extraction errors into deterministic JSON error responses.
register_error_handlers(app)
