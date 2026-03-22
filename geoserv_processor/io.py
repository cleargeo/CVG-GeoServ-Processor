# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor — Raster and vector I/O utilities.

Wraps rasterio for all raster read/write operations. Follows the same patterns
used throughout the CVG wizard suite.

Key functions
-------------
read_raster(path)               → (data: np.ndarray, profile: dict)
write_raster(path, data, profile, cfg)
load_aoi(path_or_geojson)       → list[dict]  (GeoJSON feature list)
get_resampling(name)            → rasterio.enums.Resampling
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RasterData -- lightweight in-memory raster container
# ---------------------------------------------------------------------------

@dataclass
class RasterData:
    """Lightweight container for a single-band in-memory raster.

    Attributes
    ----------
    array : np.ndarray
        2-D pixel data (float32 recommended).  NaN = nodata.
    transform : affine.Affine
        Geotransform mapping pixel coordinates to world coordinates.
    crs : str or CRS or None
        Coordinate reference system (EPSG string, rasterio CRS, or None).
    """

    array: np.ndarray
    transform: Any          # affine.Affine (optional dependency)
    crs: Optional[Any] = None

# ---------------------------------------------------------------------------
# Rasterio import guard
# ---------------------------------------------------------------------------
try:
    import rasterio
    from rasterio.crs import CRS
    from rasterio.enums import Resampling
    from rasterio.features import geometry_mask
    from rasterio.transform import from_bounds
    from rasterio.warp import calculate_default_transform, reproject as _warp_reproject
    from rasterio.merge import merge as _rasterio_merge
    import rasterio.mask as _rio_mask
    _RASTERIO_OK = True
except ImportError:
    _RASTERIO_OK = False
    log.warning("rasterio not installed — raster operations unavailable.")

try:
    import fiona
    _FIONA_OK = True
except ImportError:
    _FIONA_OK = False

try:
    import geopandas as gpd
    _GPD_OK = True
except ImportError:
    _GPD_OK = False

try:
    from shapely.geometry import shape, mapping
    _SHAPELY_OK = True
except ImportError:
    _SHAPELY_OK = False


def _require_rasterio() -> None:
    if not _RASTERIO_OK:
        raise ImportError("rasterio is required for raster I/O. pip install rasterio")


# ---------------------------------------------------------------------------
# Resampling helper
# ---------------------------------------------------------------------------

_RESAMPLING_MAP: Dict[str, Any] = {}

def get_resampling(name: str) -> Any:
    """Return rasterio.enums.Resampling by string name (case-insensitive)."""
    _require_rasterio()
    if not _RESAMPLING_MAP:
        for r in Resampling:
            _RESAMPLING_MAP[r.name.lower()] = r
    key = name.lower()
    if key not in _RESAMPLING_MAP:
        raise ValueError(
            f"Unknown resampling method '{name}'. Valid: {sorted(_RESAMPLING_MAP)}"
        )
    return _RESAMPLING_MAP[key]


# ---------------------------------------------------------------------------
# Read raster
# ---------------------------------------------------------------------------

def read_raster(
    path: str,
    band: int = 1,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Read a single band from a GeoTIFF.

    Returns
    -------
    data : np.ndarray  (float32, nodata replaced with np.nan)
    profile : dict     (rasterio profile)
    """
    _require_rasterio()
    with rasterio.open(path) as src:
        profile = dict(src.profile)
        data = src.read(band).astype(np.float32)
        nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = np.nan
    log.debug("read_raster: %s  shape=%s  CRS=%s", path, data.shape, profile.get("crs"))
    return data, profile


def read_raster_windowed(
    path: str,
    band: int = 1,
    chunk_rows: int = 1000,
):
    """Generator: yield (window, data_chunk, transform_chunk) row-strips.

    Useful for processing very large rasters without loading them fully into RAM.
    """
    _require_rasterio()
    with rasterio.open(path) as src:
        height = src.height
        nodata = src.nodata
        for row_off in range(0, height, chunk_rows):
            actual_rows = min(chunk_rows, height - row_off)
            window = rasterio.windows.Window(0, row_off, src.width, actual_rows)
            data = src.read(1, window=window).astype(np.float32)
            if nodata is not None:
                data[data == nodata] = np.nan
            win_transform = src.window_transform(window)
            yield window, data, win_transform


# ---------------------------------------------------------------------------
# Write raster
# ---------------------------------------------------------------------------

def write_raster(
    path: str,
    data: np.ndarray,
    profile: Dict[str, Any],
    compress: str = "lzw",
    tiled: bool = True,
    tile_size: int = 512,
    bigtiff: str = "IF_SAFER",
    nodata: float = -9999.0,
    overwrite: bool = True,
) -> None:
    """Write a float32 raster to a GeoTIFF.

    NaN values in data are replaced with nodata before writing.
    """
    _require_rasterio()
    out_path = Path(path)
    if out_path.exists():
        if overwrite:
            out_path.unlink()
        else:
            raise FileExistsError(f"Output file already exists: {path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    out_data = np.where(np.isnan(data), nodata, data).astype(np.float32)

    out_profile = {**profile}
    out_profile.update(
        driver="GTiff",
        dtype="float32",
        count=1,
        nodata=nodata,
        compress=compress,
        tiled=tiled,
        blockxsize=tile_size if tiled else 256,
        blockysize=tile_size if tiled else 256,
        BIGTIFF=bigtiff,
    )
    with rasterio.open(path, "w", **out_profile) as dst:
        dst.write(out_data, 1)
    log.info("write_raster: wrote %s  (%.1f MB)", path, out_path.stat().st_size / 1e6)


# ---------------------------------------------------------------------------
# AOI loading
# ---------------------------------------------------------------------------

def load_aoi(aoi_path: Optional[str] = None, aoi_geojson: Optional[Dict] = None) -> List[Dict]:
    """Load AOI geometries from a file path or inline GeoJSON.

    Returns a list of GeoJSON geometry dicts (for use with rasterio.mask).
    """
    if aoi_geojson is not None:
        geoms = aoi_geojson if isinstance(aoi_geojson, list) else [aoi_geojson]
        return geoms

    if aoi_path is None:
        raise ValueError("Must supply either aoi_path or aoi_geojson.")

    p = Path(aoi_path)
    if not p.exists():
        raise FileNotFoundError(f"AOI file not found: {aoi_path}")

    if _GPD_OK:
        gdf = gpd.read_file(aoi_path)
        return [mapping(g) for g in gdf.geometry if g is not None]
    elif _FIONA_OK:
        with fiona.open(aoi_path) as src:
            return [feat["geometry"] for feat in src]
    else:
        raise ImportError("geopandas or fiona required to load AOI files.")


# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------

def profile_from_raster(path: str) -> Dict[str, Any]:
    """Return rasterio profile dict without reading all pixel data."""
    _require_rasterio()
    with rasterio.open(path) as src:
        return dict(src.profile)


def crs_from_raster(path: str) -> Optional[Any]:
    """Return CRS object from a raster file."""
    _require_rasterio()
    with rasterio.open(path) as src:
        return src.crs


def bounds_from_raster(path: str) -> Tuple[float, float, float, float]:
    """Return (left, bottom, right, top) bounds of a raster."""
    _require_rasterio()
    with rasterio.open(path) as src:
        b = src.bounds
    return (b.left, b.bottom, b.right, b.top)