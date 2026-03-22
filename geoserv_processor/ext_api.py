"""
CVG GeoServ Processor — Extension API
Additional endpoints: metrics, config validation, version info, op catalogue.
Mounted as a plain APIRouter (no register() pattern needed).
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from geoserv_processor import __version__
from geoserv_processor.config import GeoServConfig, VALID_OPS

router = APIRouter(prefix="/api", tags=["GeoServ Extended"])

# ── In-memory metrics accumulator (populated by api_jobs.py on completion) ───
_metrics: Dict[str, Any] = {
    "jobs_submitted": 0,
    "jobs_succeeded": 0,
    "jobs_failed": 0,
    "ops_count": defaultdict(int),      # op -> count
    "elapsed_hist": [],                  # list of floats (seconds)
    "started_at": time.time(),
}


def record_job(op: str, success: bool, elapsed_s: float) -> None:
    """Called by api_jobs background runner to accumulate metrics."""
    _metrics["jobs_submitted"] += 1
    if success:
        _metrics["jobs_succeeded"] += 1
    else:
        _metrics["jobs_failed"] += 1
    _metrics["ops_count"][op] += 1
    hist = _metrics["elapsed_hist"]
    hist.append(round(elapsed_s, 3))
    if len(hist) > 500:
        _metrics["elapsed_hist"] = hist[-500:]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/metrics", summary="Processor metrics")
def get_metrics():
    """Return accumulated job metrics since last restart."""
    hist = _metrics["elapsed_hist"]
    avg_s = round(sum(hist) / len(hist), 3) if hist else None
    p95_s: Optional[float] = None
    if hist:
        sorted_hist = sorted(hist)
        idx = max(0, int(len(sorted_hist) * 0.95) - 1)
        p95_s = sorted_hist[idx]

    uptime_s = round(time.time() - _metrics["started_at"])
    return {
        "service": "geoserv-processor",
        "version": __version__,
        "uptime_seconds": uptime_s,
        "jobs": {
            "submitted": _metrics["jobs_submitted"],
            "succeeded": _metrics["jobs_succeeded"],
            "failed": _metrics["jobs_failed"],
            "success_rate": (
                round(_metrics["jobs_succeeded"] / _metrics["jobs_submitted"], 4)
                if _metrics["jobs_submitted"] > 0 else None
            ),
        },
        "ops_breakdown": dict(_metrics["ops_count"]),
        "latency": {
            "avg_s": avg_s,
            "p95_s": round(p95_s, 3) if p95_s is not None else None,
            "sample_count": len(hist),
        },
    }


class ValidateRequest(BaseModel):
    config: Dict[str, Any]


@router.post("/validate", summary="Validate GeoServConfig without running")
def validate_config(req: ValidateRequest):
    """
    Validate a GeoServConfig JSON payload.
    Returns errors list (empty = valid) without executing any jobs.
    """
    try:
        cfg = GeoServConfig.from_dict(req.config)
        errors = cfg.validate()
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Parse error: {exc}")
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "jobs_count": len(cfg.jobs) if hasattr(cfg, "jobs") and cfg.jobs else 0,
        "project_name": getattr(cfg, "project_name", None),
    }


@router.get("/ops/catalogue", summary="Full op catalogue with descriptions")
def ops_catalogue():
    """Return every supported op with a brief description."""
    descs: Dict[str, str] = {
        "reproject":    "Reproject raster to a target CRS (GDAL warp)",
        "clip":         "Clip raster to a polygon/extent mask",
        "mosaic":       "Merge multiple rasters into a single output",
        "reclassify":   "Apply a value-mapping reclassification table",
        "contour":      "Generate vector contour lines from a DEM",
        "zonal_stats":  "Compute zonal statistics for a vector zone layer",
        "convert":      "Convert raster format (GeoTIFF ↔ NetCDF ↔ ERDAS IMG, …)",
        "validate":     "Validate raster geometry, CRS, and data integrity",
    }
    return {
        "ops": [
            {"op": op, "description": descs.get(op, "No description available.")}
            for op in sorted(VALID_OPS)
        ],
        "count": len(VALID_OPS),
    }


@router.get("/version", summary="Service version info")
def version_info():
    return {
        "service": "geoserv-processor",
        "version": __version__,
        "valid_ops": sorted(VALID_OPS),
    }
