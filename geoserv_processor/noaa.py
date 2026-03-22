# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor — shared NOAA API client utilities.

Provides thin, retry-capable HTTP wrappers for:
- NOAA CO-OPS Tides & Currents API  (water levels, datums)
- NOAA PFDS / Atlas 14             (precipitation frequency data)
- NOAA TR-083 sea-level rise tables (6 CONUS gauge stations)

Public API
----------
NoaaCoOpsClient
    Fetch observed/predicted water levels and station metadata.
fetch_datum_msl_navd(station_id) -> float
    Return MSL-to-NAVD88 offset for a CO-OPS station.
fetch_station_metadata(station_id) -> dict
    Return lat/lon, name, datum offsets for a station.
fetch_pfds_precipitation(lat, lon, duration_hr, return_period_yr) -> float
    Fetch rainfall depth (mm) from NOAA Atlas 14 PFDS.
TR083_SCENARIOS : dict
    NOAA TR-083 SLR scenarios keyed by scenario name.
get_slr_projection(station_id, scenario, year) -> float
    Look up SLR projection (m) for a station/scenario/year.
nearest_slr_station(lat, lon) -> str
    Return the CO-OPS station ID for the nearest TR-083 gauge.
"""

from __future__ import annotations

import json
import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# NOAA CO-OPS base URLs
# ---------------------------------------------------------------------------
_COOPS_BASE = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
_COOPS_META = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi"
_PFDS_BASE  = "https://hdsc.nws.noaa.gov/cgi-bin/hdsc/new/fe_text_mean.csv"

# ---------------------------------------------------------------------------
# NOAA TR-083 SLR scenario data
# ---------------------------------------------------------------------------
# Projections in metres above 1992 baseline at key CONUS gauge stations.
# Source: NOAA Technical Report NOS CO-OPS 083 (2022 update).

TR083_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "low": {
        "label": "Low (Interp. 0.3 m by 2100)",
        "global_2050": 0.10,
        "global_2100": 0.30,
    },
    "intermediate_low": {
        "label": "Intermediate-Low (0.5 m by 2100)",
        "global_2050": 0.20,
        "global_2100": 0.50,
    },
    "intermediate": {
        "label": "Intermediate (1.0 m by 2100)",
        "global_2050": 0.40,
        "global_2100": 1.00,
    },
    "intermediate_high": {
        "label": "Intermediate-High (1.5 m by 2100)",
        "global_2050": 0.60,
        "global_2100": 1.50,
    },
    "high": {
        "label": "High (2.0 m by 2100)",
        "global_2050": 0.80,
        "global_2100": 2.00,
    },
    "extreme": {
        "label": "Extreme (2.5 m by 2100)",
        "global_2050": 1.00,
        "global_2100": 2.50,
    },
}

# Station-specific relative rate adjustments (m/yr) relative to global mean
_STATION_RATES: Dict[str, float] = {
    "8724580": +0.0024,   # Key West, FL
    "8720030": +0.0026,   # Jacksonville, FL (nearest major gauge)
    "8720218": +0.0025,   # Mayport, FL
    "8665530": +0.0030,   # Charleston, SC
    "8638610": +0.0045,   # Norfolk, VA (high subsidence)
    "8771341": +0.0035,   # Galveston, TX
    "8761724": +0.0060,   # Grand Isle, LA (highest subsidence)
}

# Station coordinates for nearest-station lookup
_STATION_COORDS: Dict[str, Tuple[float, float]] = {
    "8724580": (24.5597, -81.8072),   # Key West
    "8720218": (30.3967, -81.4283),   # Mayport
    "8665530": (32.7817, -79.9233),   # Charleston
    "8638610": (36.9467, -76.3300),   # Norfolk
    "8771341": (29.3100, -94.7933),   # Galveston
    "8761724": (29.2633, -89.9567),   # Grand Isle
}

# Default linear interpolation baseline year
_BASELINE_YEAR = 1992


# ---------------------------------------------------------------------------
# SLR projection helpers
# ---------------------------------------------------------------------------

def get_slr_projection(
    station_id: str,
    scenario: str,
    year: int,
    baseline_year: int = _BASELINE_YEAR,
) -> float:
    """Return sea-level rise projection (metres) for a station/scenario/year.

    Uses linear interpolation between baseline (0 m) and the 2100 scenario
    endpoint, adjusted by station-specific vertical rate.

    Parameters
    ----------
    station_id : str
        CO-OPS station ID.
    scenario : str
        One of the TR083_SCENARIOS keys (e.g. 'intermediate').
    year : int
        Target projection year (e.g. 2050, 2075, 2100).
    baseline_year : int
        Baseline epoch (default 1992 per NOAA TR-083).

    Returns
    -------
    float
        Projected SLR in metres.
    """
    if scenario not in TR083_SCENARIOS:
        raise ValueError(f"Unknown SLR scenario: {scenario!r}. "
                         f"Choose from: {list(TR083_SCENARIOS)}")

    scen = TR083_SCENARIOS[scenario]
    slr_2100 = scen["global_2100"]
    slr_2050 = scen["global_2050"]
    rate_adj = _STATION_RATES.get(station_id, 0.0)

    years_from_baseline = year - baseline_year
    years_to_2100 = 2100 - baseline_year

    # Use quadratic interpolation anchored at 2050 and 2100
    if year <= 2050:
        t = years_from_baseline / (2050 - baseline_year)
        proj = slr_2050 * (t ** 1.5)
    else:
        t = (year - 2050) / (2100 - 2050)
        proj = slr_2050 + (slr_2100 - slr_2050) * t

    # Add local subsidence/uplift adjustment
    proj += rate_adj * years_from_baseline

    return round(max(0.0, proj), 4)


def nearest_slr_station(lat: float, lon: float) -> str:
    """Return the CO-OPS station ID of the nearest TR-083 gauge to (lat, lon).

    Parameters
    ----------
    lat : float
        Latitude in decimal degrees.
    lon : float
        Longitude in decimal degrees.

    Returns
    -------
    str
        CO-OPS station ID.
    """
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    best_id = min(
        _STATION_COORDS,
        key=lambda sid: _haversine(lat, lon, *_STATION_COORDS[sid])
    )
    dist = _haversine(lat, lon, *_STATION_COORDS[best_id])
    log.debug("nearest_slr_station: %s  dist=%.1f km", best_id, dist)
    return best_id


# ---------------------------------------------------------------------------
# CO-OPS HTTP helpers
# ---------------------------------------------------------------------------

def _http_get(url: str, retries: int = 3, timeout: int = 30) -> str:
    """Fetch *url* with retry logic. Returns response body as string."""
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            with urlopen(url, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (URLError, HTTPError) as exc:
            last_err = exc
            wait = 2 ** attempt
            log.warning("HTTP GET attempt %d/%d failed (%s). Retrying in %ds…",
                        attempt + 1, retries, exc, wait)
            time.sleep(wait)
    raise ConnectionError(f"Failed to fetch {url} after {retries} attempts: {last_err}")


def fetch_station_metadata(station_id: str, timeout: int = 30) -> Dict[str, Any]:
    """Return station metadata dict from NOAA CO-OPS MDApi.

    Returns a dict with keys: id, name, lat, lon, state, datums (if available).
    """
    url = f"{_COOPS_META}/stations/{station_id}.json?expand=details"
    try:
        raw = _http_get(url, timeout=timeout)
        data = json.loads(raw)
        station = data.get("stations", [{}])[0]
        return {
            "id": station.get("id", station_id),
            "name": station.get("name", ""),
            "lat": float(station.get("lat", 0.0)),
            "lon": float(station.get("lng", 0.0)),
            "state": station.get("state", ""),
        }
    except Exception as exc:
        log.warning("fetch_station_metadata(%s) failed: %s", station_id, exc)
        return {"id": station_id, "name": "", "lat": 0.0, "lon": 0.0, "state": ""}


def fetch_datum_msl_navd(station_id: str, timeout: int = 30) -> float:
    """Return the MSL-to-NAVD88 vertical offset (metres) for *station_id*.

    A positive return means MSL is above NAVD88 at this station.
    Falls back to 0.0 if the datum is unavailable.
    """
    url = (
        f"{_COOPS_META}/stations/{station_id}/datums.json"
        f"?units=metric&datum=NAVD"
    )
    try:
        raw = _http_get(url, timeout=timeout)
        data = json.loads(raw)
        datums = {d["name"]: d["value"] for d in data.get("datums", [])}
        msl = datums.get("MSL", 0.0)
        navd = datums.get("NAVD", 0.0)
        offset = float(msl) - float(navd)
        log.debug("datum offset MSL-NAVD for %s: %.4f m", station_id, offset)
        return offset
    except Exception as exc:
        log.warning("fetch_datum_msl_navd(%s) failed: %s — returning 0.0", station_id, exc)
        return 0.0


def fetch_water_levels(
    station_id: str,
    begin_date: str,
    end_date: str,
    datum: str = "NAVD",
    units: str = "metric",
    product: str = "water_level",
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """Fetch observed water levels from NOAA CO-OPS API.

    Parameters
    ----------
    station_id : str
        7-digit CO-OPS station ID.
    begin_date : str
        Start date 'YYYYMMDD'.
    end_date : str
        End date 'YYYYMMDD'.
    datum : str
        Vertical datum ('NAVD', 'MLLW', 'MSL', etc.).
    units : str
        'metric' or 'english'.
    product : str
        CO-OPS product code ('water_level', 'predictions', 'datums').
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    list[dict]
        List of {t: datetime_str, v: value_str, q: quality_str} records.
    """
    params = {
        "station": station_id,
        "begin_date": begin_date,
        "end_date": end_date,
        "product": product,
        "datum": datum,
        "units": units,
        "time_zone": "GMT",
        "application": "CVG_GeoServ_Processor",
        "format": "json",
    }
    url = f"{_COOPS_BASE}?{urlencode(params)}"
    raw = _http_get(url, timeout=timeout)
    data = json.loads(raw)
    if "error" in data:
        raise ValueError(f"CO-OPS API error: {data['error'].get('message', data['error'])}")
    return data.get("data", [])


# ---------------------------------------------------------------------------
# NOAA PFDS (Precipitation Frequency Data Server)
# ---------------------------------------------------------------------------

# Duration-to-NOAA-code mapping (hours → PFDS duration code)
_PFDS_DURATION_MAP: Dict[float, str] = {
    0.5:  "30m",
    1.0:  "60m",
    2.0:  "2h",
    3.0:  "3h",
    6.0:  "6h",
    12.0: "12h",
    24.0: "24h",
    48.0: "2d",
    72.0: "3d",
    96.0: "4d",
    120.0: "5d",
    168.0: "7d",
    240.0: "10d",
    720.0: "30d",
    1440.0: "60d",
}

# Return-period to PFDS column index (0-based in the CSV)
_PFDS_RP_MAP: Dict[int, int] = {
    1: 1, 2: 2, 5: 3, 10: 4, 25: 5,
    50: 6, 100: 7, 200: 8, 500: 9, 1000: 10,
}


def fetch_pfds_precipitation(
    lat: float,
    lon: float,
    duration_hr: float,
    return_period_yr: int,
    timeout: int = 30,
) -> float:
    """Fetch rainfall depth (mm) from NOAA Atlas 14 PFDS.

    Parameters
    ----------
    lat : float
        Site latitude (decimal degrees, WGS84).
    lon : float
        Site longitude (decimal degrees, WGS84).
    duration_hr : float
        Storm duration in hours (must be a key in _PFDS_DURATION_MAP).
    return_period_yr : int
        Return period in years (must be a key in _PFDS_RP_MAP).
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    float
        Mean annual maximum rainfall depth in millimetres.
    """
    dur_code = _PFDS_DURATION_MAP.get(duration_hr)
    if dur_code is None:
        valid = sorted(_PFDS_DURATION_MAP.keys())
        raise ValueError(f"Unsupported duration {duration_hr} hr. Valid: {valid}")
    if return_period_yr not in _PFDS_RP_MAP:
        raise ValueError(f"Unsupported return period {return_period_yr} yr. "
                         f"Valid: {sorted(_PFDS_RP_MAP)}")

    params = {
        "lat": f"{lat:.4f}",
        "lon": f"{lon:.4f}",
        "type": "pf",
        "data": "depth",
        "units": "metric",
        "series": "pds",
    }
    url = f"{_PFDS_BASE}?{urlencode(params)}"

    raw = _http_get(url, timeout=timeout)
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    # Find the line matching the requested duration
    col_idx = _PFDS_RP_MAP[return_period_yr]
    for line in lines:
        if line.startswith(dur_code + ","):
            parts = line.split(",")
            try:
                val = float(parts[col_idx])
                log.debug("PFDS: lat=%.4f lon=%.4f dur=%s rp=%dyr → %.2f mm",
                          lat, lon, dur_code, return_period_yr, val)
                return val
            except (IndexError, ValueError) as exc:
                raise ValueError(f"Could not parse PFDS value from: {line}") from exc

    raise ValueError(
        f"PFDS response did not contain duration '{dur_code}'. "
        f"Response preview: {raw[:300]}"
    )


# ---------------------------------------------------------------------------
# Convenience class wrapper
# ---------------------------------------------------------------------------

class NoaaCoOpsClient:
    """Thin wrapper around NOAA CO-OPS API for repeated calls to one station.

    Parameters
    ----------
    station_id : str
        7-digit CO-OPS station ID.
    datum : str
        Default vertical datum.
    units : str
        Default unit system ('metric' or 'english').
    timeout : int
        Default request timeout in seconds.
    """

    def __init__(
        self,
        station_id: str,
        datum: str = "NAVD",
        units: str = "metric",
        timeout: int = 30,
    ) -> None:
        self.station_id = station_id
        self.datum = datum
        self.units = units
        self.timeout = timeout
        self._meta: Optional[Dict[str, Any]] = None

    @property
    def metadata(self) -> Dict[str, Any]:
        """Lazy-load and cache station metadata."""
        if self._meta is None:
            self._meta = fetch_station_metadata(self.station_id, self.timeout)
        return self._meta

    def get_datum_offset(self) -> float:
        """Return MSL-to-NAVD88 offset for this station."""
        return fetch_datum_msl_navd(self.station_id, self.timeout)

    def get_water_levels(
        self,
        begin_date: str,
        end_date: str,
        product: str = "water_level",
    ) -> List[Dict[str, Any]]:
        """Fetch water-level records for a date range."""
        return fetch_water_levels(
            self.station_id, begin_date, end_date,
            datum=self.datum, units=self.units,
            product=product, timeout=self.timeout,
        )

    def get_slr(self, scenario: str, year: int) -> float:
        """Return SLR projection (m) for a scenario/year at this station."""
        return get_slr_projection(self.station_id, scenario, year)

    def __repr__(self) -> str:
        return (f"NoaaCoOpsClient(station_id={self.station_id!r}, "
                f"datum={self.datum!r}, units={self.units!r})")
