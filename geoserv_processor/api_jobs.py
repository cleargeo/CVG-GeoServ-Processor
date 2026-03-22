"""
CVG GeoServ Processor — Main FastAPI Application
Job submission, status tracking, metrics, and config validation API.

Port: 8097  (configurable via APP_PORT env var)
Network: cvg-platform_cvg_net
Run: uvicorn geoserv_processor.api_jobs:app --host 0.0.0.0 --port 8097

All job-related endpoints live in ext_api.py (mounted below).
This file provides the app shell, health check, operations catalogue,
and startup/lifecycle wiring.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ── Configuration ──────────────────────────────────────────────────────────────
APP_PORT = int(os.environ.get("APP_PORT", "8097"))
SERVICE_VERSION = "1.0.0"

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CVG GeoServ Processor",
    description=(
        "RESTful job queue API for the CVG GeoServ raster geoprocessing engine.\n\n"
        "Submit `GeoServConfig` jobs (clip, reproject, mosaic, reclassify, "
        "zonal_stats, contour, convert, compound), poll status, and retrieve results.\n\n"
        "**Quick start:**\n"
        "1. `POST /api/jobs` with a `GeoServConfig` JSON body\n"
        "2. Poll `GET /api/jobs/{job_id}` until `status` is `succeeded` or `failed`\n"
        "3. Read `results` array for per-job output paths and elapsed times\n"
        "4. `GET /api/metrics` for throughput stats\n"
        "5. `POST /api/ops/validate` to dry-run validate a config\n"
    ),
    version=SERVICE_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    contact={
        "name": "Clearview Geographic LLC",
        "url": "https://www.clearviewgeographic.com",
        "email": "azelenski@clearviewgeographic.com",
    },
    license_info={"name": "Proprietary — Internal Use Only"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Health + info ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
@app.get("/api/health", tags=["System"])
def health():
    """Liveness / readiness probe."""
    return JSONResponse({
        "status": "ok",
        "service": "cvg-geoserv-processor",
        "version": SERVICE_VERSION,
        "docs": "/api/docs",
        "uptime_since": _started_at,
    })


@app.get("/api/operations", tags=["System"])
def list_operations():
    """
    List all supported raster geoprocessing operations with descriptions
    and expected input/output notes.
    """
    _op_info = {
        "clip": {
            "description": "Clip raster to a bounding box or shapefile polygon.",
            "input": "Single raster + optional clip geometry (bbox or shapefile path)",
            "output": "Clipped raster (preserves dtype and CRS)",
        },
        "reproject": {
            "description": "Reproject a raster to a target CRS (e.g. EPSG:4326, EPSG:3857).",
            "input": "Single raster + target_crs string",
            "output": "Reprojected raster",
        },
        "mosaic": {
            "description": "Merge multiple raster inputs into a single seamless output.",
            "input": "Two or more rasters with compatible band counts",
            "output": "Mosaicked raster",
        },
        "reclassify": {
            "description": "Reclassify raster values using a table of from/to rules.",
            "input": "Single raster + list of ReclassifyRule objects",
            "output": "Reclassified raster (Int16 or Float32)",
        },
        "zonal_stats": {
            "description": "Compute zonal statistics (mean, max, min, sum, count, std) from zone polygons.",
            "input": "Value raster + zone polygon file (shapefile or GeoJSON)",
            "output": "JSON/CSV table of statistics per zone",
        },
        "contour": {
            "description": "Generate vector contour lines from an elevation raster.",
            "input": "Single DEM raster + interval (e.g. 1.0 ft)",
            "output": "Contour shapefile",
        },
        "convert": {
            "description": "Convert raster format (GTiff↔PNG↔etc.) or data type (Float32↔UInt8).",
            "input": "Single raster + target format / dtype",
            "output": "Converted raster",
        },
        "compound": {
            "description": "Chain multiple ops sequentially in a single job step.",
            "input": "Raster + ordered list of sub-operations",
            "output": "Final raster after all sub-ops applied",
        },
    }

    try:
        from .config import VALID_OPS
        ops = list(VALID_OPS)
    except Exception:
        ops = list(_op_info.keys())

    return {
        "operations": [
            {"name": op, **_op_info.get(op, {"description": "", "input": "", "output": ""})}
            for op in ops
        ],
        "total": len(ops),
    }


@app.get("/", include_in_schema=False)
def root():
    """Service root — returns API map."""
    return JSONResponse({
        "service": "CVG GeoServ Processor",
        "version": SERVICE_VERSION,
        "docs": "/api/docs",
        "health": "/health",
        "endpoints": {
            "submit_job":      "POST   /api/jobs",
            "list_jobs":       "GET    /api/jobs",
            "get_job":         "GET    /api/jobs/{job_id}",
            "cancel_job":      "POST   /api/jobs/{job_id}/cancel",
            "metrics":         "GET    /api/metrics",
            "validate_config": "POST   /api/ops/validate",
            "list_operations": "GET    /api/operations",
        },
    })


# ── Mount job queue + metrics + validate router (from ext_api.py) ──────────────
from .ext_api import router as _jobs_router  # noqa: E402

app.include_router(_jobs_router)


# ── Startup timestamp tracker ──────────────────────────────────────────────────
_started_at: str = datetime.now(timezone.utc).isoformat()


@app.on_event("startup")
async def _on_startup() -> None:
    global _started_at
    _started_at = datetime.now(timezone.utc).isoformat()


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "geoserv_processor.api_jobs:app",
        host="0.0.0.0",
        port=APP_PORT,
        log_level="info",
        reload=False,
    )
