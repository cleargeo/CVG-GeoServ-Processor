# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor — Contour generation operation."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

import numpy as np

from geoserv_processor import io as _io

if TYPE_CHECKING:
    from geoserv_processor.config import JobConfig

log = logging.getLogger(__name__)


def _make_contour_levels(data: np.ndarray, cfg: Any) -> np.ndarray:
    vmin = cfg.min_value if cfg.min_value is not None else float(np.nanmin(data))
    vmax = cfg.max_value if cfg.max_value is not None else float(np.nanmax(data))
    levels = np.arange(
        cfg.base + np.ceil((vmin - cfg.base) / cfg.interval) * cfg.interval,
        vmax + cfg.interval,
        cfg.interval,
    )
    return levels


def run_contour(job: "JobConfig") -> str:
    """Generate contour lines from a raster using matplotlib/skimage or gdal_contour.

    Returns the output path.
    """
    inp = job.inputs[0]
    cfg = job.contour

    if cfg is None:
        raise ValueError("Contour job requires a 'contour' config block.")

    out_path = job.output.path if job.output else "contours.geojson"
    log.info("[contour] %s  interval=%.2f %s → %s", inp.path, cfg.interval, cfg.unit, out_path)

    data, profile = _io.read_raster(inp.path, band=inp.band)
    transform = profile["transform"]
    crs = profile.get("crs")

    levels = _make_contour_levels(data, cfg)
    log.info("[contour] %d contour levels (%.2f–%.2f)", len(levels), levels[0], levels[-1])

    try:
        from skimage import measure as _skm
        features: List[Dict[str, Any]] = []
        for level in levels:
            contours = _skm.find_contours(np.nan_to_num(data, nan=np.nanmin(data)), level)
            for c in contours:
                # Convert pixel coords to geographic coords
                coords = []
                for row, col in c:
                    x, y = transform * (col, row)
                    coords.append([x, y])
                if len(coords) < 2:
                    continue
                if cfg.geometry_type == "polygon" and len(coords) >= 4:
                    if coords[0] != coords[-1]:
                        coords.append(coords[0])
                    geom = {"type": "Polygon", "coordinates": [coords]}
                else:
                    geom = {"type": "LineString", "coordinates": coords}
                features.append({
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {cfg.elevation_field: round(float(level), 4), "unit": cfg.unit},
                })
        geojson = {"type": "FeatureCollection", "features": features}
        if crs:
            geojson["crs"] = {"type": "name", "properties": {"name": str(crs)}}

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        fmt = cfg.output_format.upper()
        if fmt == "GEOJSON":
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(geojson, fh, indent=2)
        elif fmt in ("SHAPEFILE", "GPKG"):
            try:
                import geopandas as gpd
                import shapely.geometry as sgeom
                geoms = [sgeom.shape(f["geometry"]) for f in features]
                props = [f["properties"] for f in features]
                gdf = gpd.GeoDataFrame(props, geometry=geoms, crs=str(crs) if crs else None)
                if fmt == "SHAPEFILE":
                    gdf.to_file(out_path)
                else:
                    gdf.to_file(out_path, driver="GPKG")
            except ImportError:
                raise ImportError("geopandas + shapely required for Shapefile/GPKG contour output.")
        else:
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(geojson, fh, indent=2)

    except ImportError:
        raise ImportError("scikit-image required for contour generation: pip install scikit-image")

    log.info("[contour] ✓ %d features → %s", len(features), out_path)
    return out_path
