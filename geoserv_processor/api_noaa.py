# -*- coding: utf-8 -*-
# =============================================================================
# CVG GeoServ Processor — NOAA Data API  (APIRouter)
# Mount at prefix /api/noaa in web.py
# =============================================================================
"""
REST endpoints exposing the NOAA CO-OPS + PFDS + TR-083 SLR library.

Endpoints
---------
GET /api/noaa/stations/nearest          Nearest TR-083 gauge to a lat/lon
GET /api/noaa/stations/{station_id}     Station metadata (name, lat, lon)
GET /api/noaa/stations/{station_id}/datums   MSL-NAVD88 datum offset
GET /api/noaa/stations/{station_id}/levels   Observed water levels for a date range
GET /api/noaa/stations/{station_id}/slr      SLR projections for all scenarios
GET /api/noaa/slr/scenarios             List available SLR scenario names
GET /api/noaa/slr/{station_id}/{scenario}/{year}  Single SLR value
GET /api/noaa/pfds                      NOAA Atlas 14 rainfall depth
GET /api/noaa/pfds/batch                Multiple PFDS lookups in one call
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

log = logging.getLogger("cvg.geoserv.noaa")

router = APIRouter(prefix="/api/noaa", tags=["NOAA Data"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class PfdsRequest(BaseModel):
    lat: float                    = Field(..., description="Site latitude (WGS84)")
    lon: float                    = Field(..., description="Site longitude (WGS84)")
    duration_hr: float            = Field(..., description="Storm duration (hours)")
    return_period_yr: int         = Field(..., description="Return period (years)")


class PfdsBatchItem(BaseModel):
    lat: float
    lon: float
    duration_hr: float
    return_period_yr: int
    label: Optional[str] = None


class PfdsBatchRequest(BaseModel):
    items: List[PfdsBatchItem]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_sync(fn, *args, **kwargs):
    """Run a blocking function in the default executor."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, lambda: fn(*args, **kwargs))


def _noaa_import():
    """Lazy import to avoid top-level import cost."""
    from geoserv_processor.noaa import (
        fetch_station_metadata,
        fetch_datum_msl_navd,
        fetch_water_levels,
        fetch_pfds_precipitation,
        get_slr_projection,
        nearest_slr_station,
        TR083_SCENARIOS,
        _STATION_COORDS,
    )
    return (
        fetch_station_metadata,
        fetch_datum_msl_navd,
        fetch_water_levels,
        fetch_pfds_precipitation,
        get_slr_projection,
        nearest_slr_station,
        TR083_SCENARIOS,
        _STATION_COORDS,
    )


# ---------------------------------------------------------------------------
# SLR Scenario catalogue
# ---------------------------------------------------------------------------

@router.get("/slr/scenarios", summary="List all NOAA TR-083 SLR scenarios")
def list_slr_scenarios():
    """Return available sea-level rise scenario names and descriptions."""
    (_, _, _, _, _, _, TR083_SCENARIOS, _) = _noaa_import()
    return {
        "scenarios": [
            {"id": k, **{kk: vv for kk, vv in v.items()}}
            for k, v in TR083_SCENARIOS.items()
        ]
    }


# ---------------------------------------------------------------------------
# Nearest TR-083 gauge
# ---------------------------------------------------------------------------

@router.get("/stations/nearest", summary="Nearest TR-083 SLR gauge station")
async def nearest_station(
    lat: float = Query(..., description="Latitude (decimal degrees)"),
    lon: float = Query(..., description="Longitude (decimal degrees)"),
):
    """Return the NOAA CO-OPS station closest to the given coordinates."""
    (fetch_station_metadata, _, _, _, _, nearest_slr_station, _, _STATION_COORDS) = _noaa_import()
    try:
        station_id = nearest_slr_station(lat, lon)
        meta = await asyncio.get_event_loop().run_in_executor(
            None, fetch_station_metadata, station_id
        )
        coords = _STATION_COORDS.get(station_id, (None, None))
        import math
        def haversine(lat1, lon1, lat2, lon2):
            R = 6371.0
            phi1, phi2 = math.radians(lat1), math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlam = math.radians(lon2 - lon1)
            a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        dist_km = haversine(lat, lon, coords[0], coords[1]) if coords[0] else None
        return {
            "query_lat": lat,
            "query_lon": lon,
            "station": meta,
            "distance_km": round(dist_km, 1) if dist_km else None,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# Station metadata
# ---------------------------------------------------------------------------

@router.get("/stations/{station_id}", summary="Station metadata")
async def get_station(station_id: str):
    """Return name, lat, lon, state for a NOAA CO-OPS station."""
    (fetch_station_metadata, _, _, _, _, _, _, _) = _noaa_import()
    try:
        meta = await asyncio.get_event_loop().run_in_executor(
            None, fetch_station_metadata, station_id
        )
        return meta
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/stations/{station_id}/datums", summary="MSL-NAVD88 datum offset")
async def get_datums(station_id: str):
    """Return the MSL-to-NAVD88 vertical offset in metres for a station."""
    (_, fetch_datum_msl_navd, _, _, _, _, _, _) = _noaa_import()
    try:
        offset = await asyncio.get_event_loop().run_in_executor(
            None, fetch_datum_msl_navd, station_id
        )
        return {
            "station_id": station_id,
            "msl_to_navd88_m": offset,
            "note": "Positive value means MSL is above NAVD88 at this station",
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# Water levels
# ---------------------------------------------------------------------------

@router.get("/stations/{station_id}/levels", summary="Observed water levels")
async def get_water_levels(
    station_id: str,
    begin_date: str = Query(..., description="Start date YYYYMMDD"),
    end_date: str   = Query(..., description="End date YYYYMMDD"),
    datum: str      = Query("NAVD", description="Vertical datum"),
    units: str      = Query("metric", description="'metric' or 'english'"),
    product: str    = Query("water_level", description="CO-OPS product code"),
):
    """Fetch observed or predicted water levels from NOAA CO-OPS API."""
    (_, _, fetch_water_levels, _, _, _, _, _) = _noaa_import()
    try:
        data = await asyncio.get_event_loop().run_in_executor(
            None, fetch_water_levels, station_id, begin_date, end_date, datum, units, product
        )
        return {
            "station_id": station_id,
            "begin_date": begin_date,
            "end_date": end_date,
            "datum": datum,
            "units": units,
            "product": product,
            "count": len(data),
            "data": data,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# SLR projections
# ---------------------------------------------------------------------------

@router.get("/stations/{station_id}/slr", summary="SLR projections for all scenarios")
def get_station_slr(
    station_id: str,
    years: str = Query("2030,2050,2075,2100", description="Comma-separated projection years"),
):
    """Return SLR projections (metres) for a station across all scenarios and years."""
    (_, _, _, _, get_slr_projection, _, TR083_SCENARIOS, _) = _noaa_import()
    target_years = [int(y.strip()) for y in years.split(",") if y.strip().isdigit()]
    if not target_years:
        raise HTTPException(status_code=422, detail="Invalid years parameter")

    projections: Dict[str, Dict[int, float]] = {}
    for scenario in TR083_SCENARIOS:
        projections[scenario] = {}
        for year in target_years:
            projections[scenario][year] = get_slr_projection(station_id, scenario, year)

    return {
        "station_id": station_id,
        "years": target_years,
        "scenarios": projections,
        "scenario_labels": {k: v["label"] for k, v in TR083_SCENARIOS.items()},
    }


@router.get("/slr/{station_id}/{scenario}/{year}", summary="Single SLR projection value")
def get_slr_value(station_id: str, scenario: str, year: int):
    """Return a single SLR projection value (metres) for a station/scenario/year."""
    (_, _, _, _, get_slr_projection, _, TR083_SCENARIOS, _) = _noaa_import()
    if scenario not in TR083_SCENARIOS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown scenario '{scenario}'. Available: {list(TR083_SCENARIOS)}",
        )
    value = get_slr_projection(station_id, scenario, year)
    return {
        "station_id": station_id,
        "scenario":   scenario,
        "scenario_label": TR083_SCENARIOS[scenario]["label"],
        "year":       year,
        "slr_m":      value,
    }


# ---------------------------------------------------------------------------
# PFDS (Atlas 14 rainfall)
# ---------------------------------------------------------------------------

@router.get("/pfds", summary="NOAA Atlas 14 rainfall depth")
async def get_pfds(
    lat:              float = Query(..., description="Site latitude"),
    lon:              float = Query(..., description="Site longitude"),
    duration_hr:      float = Query(..., description="Storm duration (hours)"),
    return_period_yr: int   = Query(..., description="Return period (years)"),
):
    """Fetch mean annual maximum rainfall depth (mm) from NOAA Atlas 14 PFDS."""
    (_, _, _, fetch_pfds_precipitation, _, _, _, _) = _noaa_import()
    try:
        depth_mm = await asyncio.get_event_loop().run_in_executor(
            None, fetch_pfds_precipitation, lat, lon, duration_hr, return_period_yr
        )
        return {
            "lat": lat,
            "lon": lon,
            "duration_hr": duration_hr,
            "return_period_yr": return_period_yr,
            "depth_mm": depth_mm,
            "depth_in": round(depth_mm / 25.4, 3),
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/pfds/batch", summary="Batch PFDS lookups")
async def get_pfds_batch(req: PfdsBatchRequest):
    """Fetch multiple NOAA Atlas 14 rainfall values in a single request."""
    (_, _, _, fetch_pfds_precipitation, _, _, _, _) = _noaa_import()

    async def _fetch_one(item: PfdsBatchItem) -> dict:
        try:
            depth_mm = await asyncio.get_event_loop().run_in_executor(
                None, fetch_pfds_precipitation,
                item.lat, item.lon, item.duration_hr, item.return_period_yr
            )
            return {
                "label": item.label,
                "lat": item.lat, "lon": item.lon,
                "duration_hr": item.duration_hr,
                "return_period_yr": item.return_period_yr,
                "depth_mm": depth_mm,
                "depth_in": round(depth_mm / 25.4, 3),
                "error": None,
            }
        except Exception as exc:
            return {
                "label": item.label,
                "lat": item.lat, "lon": item.lon,
                "duration_hr": item.duration_hr,
                "return_period_yr": item.return_period_yr,
                "depth_mm": None,
                "depth_in": None,
                "error": str(exc),
            }

    results = await asyncio.gather(*[_fetch_one(item) for item in req.items])
    return {"count": len(results), "results": list(results)}
