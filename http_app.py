from __future__ import annotations

from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware
from starlette.responses import JSONResponse

from config import get_settings
from mcp_app import mcp

# Add custom routes to the MCP app for health checks
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
        "runner_dir": str(settings.runner_dir),
    })


# Get the MCP streamable HTTP app - this is the main app
# It handles /mcp internally and now also has /healthz and /readyz
app = mcp.streamable_http_app()

# Add CORS middleware directly to the Starlette app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
