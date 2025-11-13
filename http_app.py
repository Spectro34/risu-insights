"""
HTTP Transport for MCP Server

Supports streamable-http and SSE endpoints for direct HTTP clients.
"""

from __future__ import annotations

from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from config import get_settings
from mcp_app import mcp

# Health check endpoints
@mcp.custom_route("/healthz", methods=["GET"])
async def healthcheck(request):
    return JSONResponse({"status": "ok"})


@mcp.custom_route("/readyz", methods=["GET"])
async def readiness(request):
    settings = get_settings()
    inventory_ok = settings.inventory_path.exists()
    return JSONResponse({
        "status": "ready" if inventory_ok else "degraded",
        "inventory": str(settings.inventory_path),
    })


# Get the MCP streamable HTTP app
# Supports: /mcp (streamable-http) and /sse (Server-Sent Events)
app = mcp.streamable_http_app()

# CORS middleware for web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

