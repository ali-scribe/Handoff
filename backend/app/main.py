"""Handoff backend application entrypoint.

Creates the FastAPI app and wires up routes plus the extraction-error handler.

Loads ``backend/.env`` into the process environment at startup (if present) so
local development can supply Gemini settings via a .env file. Real shell/server
environment variables take precedence (``override=False``), so deployed
environments that set the vars directly are unaffected. Config is still read
from ``os.environ`` by ``load_gemini_config`` - this only populates it.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load backend/.env (this file lives at backend/app/main.py, so the .env is one
# directory up). Loaded before the app/config is used; does not override vars
# already present in the environment.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

from app.api import analyze, clarification, health
from app.api.errors import register_error_handlers

app = FastAPI(title="Handoff")

# Optional CORS support for cross-origin deployments (e.g. the frontend served
# from a different origin than this API). Configured entirely via the
# HANDOFF_CORS_ALLOW_ORIGINS environment variable: a comma-separated list of
# allowed origins. When unset or empty, NO CORS middleware is added, which
# preserves the previous behavior and is correct for same-origin deployments
# (frontend and API behind one reverse proxy). This adds configuration only; it
# changes no request/response behavior when the variable is not set.
_cors_origins = [
    origin.strip()
    for origin in os.environ.get("HANDOFF_CORS_ALLOW_ORIGINS", "").split(",")
    if origin.strip()
]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

# All API routes live under the /api prefix so the frontend can proxy /api.
app.include_router(health.router, prefix="/api")
app.include_router(analyze.router, prefix="/api")
app.include_router(clarification.router, prefix="/api")

# Translate typed extraction errors into deterministic JSON error responses.
register_error_handlers(app)