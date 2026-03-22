# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor — shared utility functions.

Miscellaneous coordinate helpers, unit converters, date utilities, and
string/formatting tools used across the CVG Wizard Suite.

Public API
----------
ft_to_m(value) -> float
m_to_ft(value) -> float
in_to_mm(value) -> float
mm_to_in(value) -> float
haversine_km(lat1, lon1, lat2, lon2) -> float
validate_lat_lon(lat, lon) -> None
bbox_from_point(lat, lon, radius_km) -> tuple
return_period_to_aep(rp_yr) -> float
aep_to_return_period(aep) -> float
slugify(text) -> str
timestamp_str(fmt) -> str
safe_mkdir(path) -> Path
flatten_dict(d, sep) -> dict
"""

from __future__ import annotations

import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------

def ft_to_m(value: float) -> float:
    """Convert feet to metres."""
    return value * 0.3048


def m_to_ft(value: float) -> float:
    """Convert metres to feet."""
    return value / 0.3048


def in_to_mm(value: float) -> float:
    """Convert inches to millimetres."""
    return value * 25.4


def mm_to_in(value: float) -> float:
    """Convert millimetres to inches."""
    return value / 25.4


def cm_to_m(value: float) -> float:
    """Convert centimetres to metres."""
    return value / 100.0


def m_to_cm(value: float) -> float:
    """Convert metres to centimetres."""
    return value * 100.0


def sqm_to_sqft(value: float) -> float:
    """Convert square metres to square feet."""
    return value * 10.7639


def sqft_to_sqm(value: float) -> float:
    """Convert square feet to square metres."""
    return value / 10.7639


def sqm_to_acres(value: float) -> float:
    """Convert square metres to acres."""
    return value / 4046.8564


def sqm_to_sqkm(value: float) -> float:
    """Convert square metres to square kilometres."""
    return value / 1_000_000.0


# ---------------------------------------------------------------------------
# Coordinate utilities
# ---------------------------------------------------------------------------

def haversine_km(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """Return great-circle distance in kilometres between two lat/lon points.

    Parameters
    ----------
    lat1, lon1 : float
        Origin coordinates (decimal degrees).
    lat2, lon2 : float
        Destination coordinates (decimal degrees).

    Returns
    -------
    float
        Distance in kilometres.
    """
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def validate_lat_lon(lat: float, lon: float) -> None:
    """Raise ValueError if lat/lon are out of valid range.

    Parameters
    ----------
    lat : float
        Latitude in decimal degrees.
    lon : float
        Longitude in decimal degrees.

    Raises
    ------
    ValueError
        If lat is not in [-90, 90] or lon is not in [-180, 180].
    """
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Latitude {lat} is out of range [-90, 90].")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"Longitude {lon} is out of range [-180, 180].")


def bbox_from_point(
    lat: float,
    lon: float,
    radius_km: float,
) -> Tuple[float, float, float, float]:
    """Return a bounding box (west, south, east, north) around a point.

    Parameters
    ----------
    lat : float
        Centre latitude.
    lon : float
        Centre longitude.
    radius_km : float
        Half-width/half-height of the box in kilometres.

    Returns
    -------
    tuple[float, float, float, float]
        (west, south, east, north) in decimal degrees.
    """
    delta_lat = radius_km / 111.32
    delta_lon = radius_km / (111.32 * math.cos(math.radians(lat)))
    return (
        lon - delta_lon,
        lat - delta_lat,
        lon + delta_lon,
        lat + delta_lat,
    )


def decimal_to_dms(decimal_deg: float) -> Tuple[int, int, float]:
    """Convert decimal degrees to (degrees, minutes, seconds)."""
    sign = -1 if decimal_deg < 0 else 1
    d = abs(decimal_deg)
    deg = int(d)
    min_f = (d - deg) * 60
    mins = int(min_f)
    secs = (min_f - mins) * 60
    return (sign * deg, mins, secs)


# ---------------------------------------------------------------------------
# Hydrology helpers
# ---------------------------------------------------------------------------

def return_period_to_aep(rp_yr: float) -> float:
    """Convert return period (years) to Annual Exceedance Probability [0–1].

    Example: 100-year event → AEP = 0.01 (1 %)
    """
    if rp_yr <= 0:
        raise ValueError("Return period must be > 0.")
    return 1.0 / rp_yr


def aep_to_return_period(aep: float) -> float:
    """Convert Annual Exceedance Probability [0–1] to return period (years)."""
    if not (0 < aep <= 1.0):
        raise ValueError("AEP must be in (0, 1].")
    return 1.0 / aep


def tr55_runoff_depth(rainfall_mm: float, curve_number: float) -> float:
    """Compute direct runoff depth (mm) using NRCS TR-55 method.

    Parameters
    ----------
    rainfall_mm : float
        Total precipitation depth (mm).
    curve_number : float
        NRCS Curve Number (0 < CN <= 100).

    Returns
    -------
    float
        Direct runoff depth in millimetres.
    """
    if not (0 < curve_number <= 100):
        raise ValueError("Curve Number must be in (0, 100].")
    S_in = (1000.0 / curve_number) - 10.0          # potential max retention (in)
    S_mm = S_in * 25.4                               # convert to mm
    Ia_mm = 0.2 * S_mm                               # initial abstraction
    if rainfall_mm <= Ia_mm:
        return 0.0
    Q = (rainfall_mm - Ia_mm) ** 2 / (rainfall_mm - Ia_mm + S_mm)
    return max(0.0, Q)


def rainfall_intensity_mm_hr(depth_mm: float, duration_hr: float) -> float:
    """Return average rainfall intensity (mm/hr) for a depth and duration."""
    if duration_hr <= 0:
        raise ValueError("Duration must be > 0.")
    return depth_mm / duration_hr


# ---------------------------------------------------------------------------
# String utilities
# ---------------------------------------------------------------------------

def slugify(text: str, separator: str = "_") -> str:
    """Convert *text* to a safe filename slug.

    Replaces spaces and special characters with *separator*.

    Example
    -------
    >>> slugify("100-Year Flood Depth (NAVD88)")
    '100_year_flood_depth_navd88'
    """
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s\-]+", separator, text)
    return text.strip(separator)


def timestamp_str(fmt: str = "%Y%m%d_%H%M%S") -> str:
    """Return current UTC time as a formatted string."""
    return datetime.now(tz=timezone.utc).strftime(fmt)


def human_bytes(size_bytes: int) -> str:
    """Human-readable file size string.

    Example
    -------
    >>> human_bytes(1_234_567)
    '1.18 MB'
    """
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0  # type: ignore
    return f"{size_bytes:.2f} PB"


# ---------------------------------------------------------------------------
# File / path utilities
# ---------------------------------------------------------------------------

def safe_mkdir(path: Union[str, Path]) -> Path:
    """Create *path* and all parents; return as absolute Path."""
    p = Path(path).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def unique_path(path: Union[str, Path]) -> Path:
    """Return *path* with a numeric suffix if it already exists.

    Example
    -------
    If ``output.tif`` exists, returns ``output_1.tif``, then ``output_2.tif``, etc.
    """
    p = Path(path)
    if not p.exists():
        return p
    stem, suffix = p.stem, p.suffix
    parent = p.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# Dict utilities
# ---------------------------------------------------------------------------

def flatten_dict(
    d: Dict[str, Any],
    sep: str = ".",
    _prefix: str = "",
) -> Dict[str, Any]:
    """Flatten a nested dict into a single-level dict with *sep*-joined keys.

    Example
    -------
    >>> flatten_dict({"a": {"b": 1, "c": 2}, "d": 3})
    {'a.b': 1, 'a.c': 2, 'd': 3}
    """
    result: Dict[str, Any] = {}
    for k, v in d.items():
        key = f"{_prefix}{sep}{k}" if _prefix else k
        if isinstance(v, dict):
            result.update(flatten_dict(v, sep=sep, _prefix=key))
        else:
            result[key] = v
    return result


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge *override* into *base* and return a new dict."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result