# -*- coding: utf-8 -*-
# =============================================================================
# CVG GeoServ Processor — Per-Operation Shortcut API  (APIRouter)
# Mount at prefix /api/ops in web.py
# =============================================================================
"""
Shortcut endpoints for each supported geoprocessing operation.
Each endpoint accepts the specific parameters for its operation,
builds a GeoServConfig internally, and runs the job synchronously
(use /api/jobs/submit for async execution).

Endpoints
---------
GET  /api/ops                   List all supported operations with schemas
POST /api/ops/reproject         Reproject a raster to a target CRS
POST /api/ops/clip              Clip a raster to a bbox or polygon
POST /api/ops/mosaic            Mosaic multiple rasters into one
POST /api/ops/reclassify        Reclassify raster values
POST /api/ops/contour           Generate contour lines from a DEM
POST /api/ops/zonal_stats       Compute zonal statistics
POST /api/ops/convert           Convert raster format/compression
POST /api/ops/validate          Validate a config without executing
"""
from __future__ import annotations

import asyncio
import time
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger("cvg.geoserv.ops")

router = APIRouter(prefix="/api/ops", tags=["Operations"])

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class RasterInput(BaseModel):
    path: str = Field(..., description="Input raster path (absolute or /data/ mounted)")


class RasterOutput(BaseModel):
    path: str = Field(..., description="Output path")
    compress: Optional[str] = Field("lzw", description="Compression: lzw, deflate, none")
    tiled: bool = True
    nodata: Optional[float] = None


def _run_single_op(job_dict: dict) -> dict:
    """Build a minimal GeoServConfig and run it synchronously."""
    from geoserv_processor.config import GeoServConfig
    from geoserv_processor.processing import run_geoserv_job
    cfg = GeoServConfig.from_dict(job_dict)
    errors = cfg.validate()
    if errors:
        raise ValueError(f"Config validation errors: {errors}")
    t0 = time.monotonic()
    results = run_geoserv_job(cfg)
    elapsed = round(time.monotonic() - t0, 2)
    n_ok = sum(1 for r in results if r["status"] == "success")
    return {
        "jobs_total": len(results),
        "jobs_succeeded": n_ok,
        "jobs_failed": len(results) - n_ok,
        "elapsed_s": elapsed,
        "results": results,
    }


async def _run_async(job_dict: dict) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_single_op, job_dict)


# ---------------------------------------------------------------------------
# Ops catalogue
# ---------------------------------------------------------------------------

@router.get("", summary="List supported operations")
def list_ops():
    """Return all supported geoprocessing operations with parameter schemas."""
    from geoserv_processor.config import VALID_OPS
    from geoserv_processor import __version__
    ops = []
    for op in sorted(VALID_OPS):
        ops.append({
            "op": op,
            "endpoint": f"/api/ops/{op}",
            "method": "POST",
            "async_endpoint": "/api/jobs/submit",
        })
    return {"version": __version__, "count": len(ops), "operations": ops}


# ---------------------------------------------------------------------------
# Reproject
# ---------------------------------------------------------------------------

class ReprojectRequest(BaseModel):
    input_path: str       = Field(..., description="Input raster path")
    output_path: str      = Field(..., description="Output raster path")
    crs: str              = Field("EPSG:4326", description="Target CRS (e.g. EPSG:4326)")
    resampling: str       = Field("bilinear", description="Resampling method")
    compress: str         = Field("lzw")
    tiled: bool           = True
    project_name: str     = Field("reproject", description="Job label")


@router.post("/reproject", summary="Reproject a raster")
async def run_reproject(req: ReprojectRequest):
    """Reproject a raster to the specified CRS."""
    job = {
        "project_name": req.project_name,
        "resume": False,
        "validate_inputs_exist": False,
        "stop_on_error": True,
        "jobs": [{
            "op": "reproject",
            "label": "reproject",
            "enabled": True,
            "inputs": [{"path": req.input_path}],
            "output": {"path": req.output_path, "compress": req.compress, "tiled": req.tiled},
            "reproject": {"crs": req.crs, "resampling": req.resampling},
        }],
    }
    try:
        return await _run_async(job)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Clip
# ---------------------------------------------------------------------------

class ClipRequest(BaseModel):
    input_path: str       = Field(..., description="Input raster path")
    output_path: str      = Field(..., description="Output raster path")
    bbox: Optional[List[float]] = Field(None, description="[minx, miny, maxx, maxy] in same CRS")
    mask_path: Optional[str]   = Field(None, description="Vector mask path (.shp/.geojson)")
    crs: Optional[str]         = Field(None, description="Clip bbox CRS (default: raster CRS)")
    compress: str              = Field("lzw")
    project_name: str          = Field("clip")


@router.post("/clip", summary="Clip a raster to a bounding box or polygon")
async def run_clip(req: ClipRequest):
    """Clip a raster to a bounding box or vector mask."""
    if req.bbox is None and req.mask_path is None:
        raise HTTPException(status_code=422, detail="Provide either bbox or mask_path")
    clip_cfg: dict = {}
    if req.bbox:
        clip_cfg["bbox"] = req.bbox
        if req.crs:
            clip_cfg["crs"] = req.crs
    if req.mask_path:
        clip_cfg["mask"] = req.mask_path
    job = {
        "project_name": req.project_name,
        "resume": False,
        "validate_inputs_exist": False,
        "stop_on_error": True,
        "jobs": [{
            "op": "clip",
            "label": "clip",
            "enabled": True,
            "inputs": [{"path": req.input_path}],
            "output": {"path": req.output_path, "compress": req.compress, "tiled": True},
            "clip": clip_cfg,
        }],
    }
    try:
        return await _run_async(job)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Mosaic
# ---------------------------------------------------------------------------

class MosaicRequest(BaseModel):
    input_paths: List[str] = Field(..., description="List of raster paths to mosaic")
    output_path: str       = Field(..., description="Output mosaic path")
    crs: Optional[str]     = Field(None, description="Output CRS (defaults to first input)")
    resampling: str        = Field("nearest")
    compress: str          = Field("lzw")
    project_name: str      = Field("mosaic")


@router.post("/mosaic", summary="Mosaic multiple rasters")
async def run_mosaic(req: MosaicRequest):
    """Mosaic (merge) multiple raster tiles into a single output file."""
    job = {
        "project_name": req.project_name,
        "resume": False,
        "validate_inputs_exist": False,
        "stop_on_error": True,
        "jobs": [{
            "op": "mosaic",
            "label": "mosaic",
            "enabled": True,
            "inputs": [{"path": p} for p in req.input_paths],
            "output": {"path": req.output_path, "compress": req.compress, "tiled": True},
            "mosaic": {"resampling": req.resampling, **({"crs": req.crs} if req.crs else {})},
        }],
    }
    try:
        return await _run_async(job)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Reclassify
# ---------------------------------------------------------------------------

class ReclassifyRequest(BaseModel):
    input_path: str   = Field(..., description="Input raster path")
    output_path: str  = Field(..., description="Output raster path")
    rules: List[Dict[str, Any]] = Field(
        ...,
        description="Reclassification rules: [{min, max, new_value}, ...]"
    )
    compress: str     = Field("lzw")
    project_name: str = Field("reclassify")


@router.post("/reclassify", summary="Reclassify raster values")
async def run_reclassify(req: ReclassifyRequest):
    """Reclassify raster cell values using a lookup/range table."""
    job = {
        "project_name": req.project_name,
        "resume": False,
        "validate_inputs_exist": False,
        "stop_on_error": True,
        "jobs": [{
            "op": "reclassify",
            "label": "reclassify",
            "enabled": True,
            "inputs": [{"path": req.input_path}],
            "output": {"path": req.output_path, "compress": req.compress, "tiled": True},
            "reclassify": {"rules": req.rules},
        }],
    }
    try:
        return await _run_async(job)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Contour
# ---------------------------------------------------------------------------

class ContourRequest(BaseModel):
    input_path: str     = Field(..., description="DEM raster path")
    output_path: str    = Field(..., description="Output vector path (.shp or .geojson)")
    interval: float     = Field(..., description="Contour interval in raster units")
    base: float         = Field(0.0, description="Starting contour value")
    project_name: str   = Field("contour")


@router.post("/contour", summary="Generate contour lines from DEM")
async def run_contour(req: ContourRequest):
    """Generate vector contour lines from a digital elevation model."""
    job = {
        "project_name": req.project_name,
        "resume": False,
        "validate_inputs_exist": False,
        "stop_on_error": True,
        "jobs": [{
            "op": "contour",
            "label": "contour",
            "enabled": True,
            "inputs": [{"path": req.input_path}],
            "output": {"path": req.output_path},
            "contour": {"interval": req.interval, "base": req.base},
        }],
    }
    try:
        return await _run_async(job)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Zonal Statistics
# ---------------------------------------------------------------------------

class ZonalStatsRequest(BaseModel):
    raster_path: str           = Field(..., description="Input raster path")
    zones_path: str            = Field(..., description="Zone polygon vector path")
    output_path: str           = Field(..., description="Output CSV or GeoJSON path")
    stats: List[str]           = Field(
        default=["mean", "min", "max", "std"],
        description="Statistics to compute: mean, min, max, std, sum, count"
    )
    zone_field: Optional[str]  = Field(None, description="Zone identifier field name")
    project_name: str          = Field("zonal_stats")


@router.post("/zonal_stats", summary="Compute zonal statistics")
async def run_zonal_stats(req: ZonalStatsRequest):
    """Compute raster statistics aggregated by polygon zones."""
    job = {
        "project_name": req.project_name,
        "resume": False,
        "validate_inputs_exist": False,
        "stop_on_error": True,
        "jobs": [{
            "op": "zonal_stats",
            "label": "zonal_stats",
            "enabled": True,
            "inputs": [{"path": req.raster_path}, {"path": req.zones_path}],
            "output": {"path": req.output_path},
            "zonal_stats": {
                "stats": req.stats,
                **({"zone_field": req.zone_field} if req.zone_field else {}),
            },
        }],
    }
    try:
        return await _run_async(job)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Format Convert
# ---------------------------------------------------------------------------

class ConvertRequest(BaseModel):
    input_path: str    = Field(..., description="Input raster path")
    output_path: str   = Field(..., description="Output path (extension determines format)")
    compress: str      = Field("lzw", description="Compression algorithm")
    tiled: bool        = True
    overview: bool     = Field(False, description="Build overview pyramids")
    project_name: str  = Field("convert")


@router.post("/convert", summary="Convert raster format / compression")
async def run_convert(req: ConvertRequest):
    """Re-encode a raster file (format conversion, compression change, tiling)."""
    job = {
        "project_name": req.project_name,
        "resume": False,
        "validate_inputs_exist": False,
        "stop_on_error": True,
        "jobs": [{
            "op": "convert",
            "label": "convert",
            "enabled": True,
            "inputs": [{"path": req.input_path}],
            "output": {
                "path": req.output_path,
                "compress": req.compress,
                "tiled": req.tiled,
            },
            "convert": {"overview": req.overview},
        }],
    }
    try:
        return await _run_async(job)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Config Validate
# ---------------------------------------------------------------------------

class ValidateRequest(BaseModel):
    config: Dict[str, Any] = Field(..., description="GeoServConfig JSON to validate")


@router.post("/validate", summary="Validate a GeoServConfig without executing")
def validate_config(req: ValidateRequest):
    """Validate a GeoServConfig JSON object without running any operations."""
    try:
        from geoserv_processor.config import GeoServConfig
        cfg = GeoServConfig.from_dict(req.config)
        errors = cfg.validate()
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "jobs_count": len(cfg.jobs) if hasattr(cfg, "jobs") else 0,
        }
    except Exception as exc:
        return {"valid": False, "errors": [str(exc)], "jobs_count": 0}
