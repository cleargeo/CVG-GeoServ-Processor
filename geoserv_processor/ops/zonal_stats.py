# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor — Zonal statistics operation."""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

import numpy as np

from geoserv_processor import io as _io

if TYPE_CHECKING:
    from geoserv_processor.config import JobConfig

log = logging.getLogger(__name__)


def _compute_stats(values: np.ndarray, stats: List[str]) -> Dict[str, Any]:
    v = values[~np.isnan(values)]
    result: Dict[str, Any] = {}
    for s in stats:
        if s == "min":
            result["min"] = float(np.nanmin(v)) if len(v) else None
        elif s == "max":
            result["max"] = float(np.nanmax(v)) if len(v) else None
        elif s == "mean":
            result["mean"] = float(np.nanmean(v)) if len(v) else None
        elif s == "sum":
            result["sum"] = float(np.nansum(v)) if len(v) else None
        elif s == "count":
            result["count"] = int(np.sum(~np.isnan(values)))
        elif s == "std":
            result["std"] = float(np.nanstd(v)) if len(v) else None
        elif s == "median":
            result["median"] = float(np.nanmedian(v)) if len(v) else None
    return result


def run_zonal_stats(job: "JobConfig") -> str:
    """Compute zonal statistics over a raster using polygon zones.

    Outputs CSV, JSON, or GeoJSON depending on cfg.output_format.
    Returns the output path.
    """
    import rasterio
    from rasterio.features import geometry_mask

    inp = job.inputs[0]
    cfg = job.zonal_stats

    if cfg is None:
        raise ValueError("Zonal stats job requires a 'zonal_stats' config block.")

    log.info("[zonal_stats] %s zones=%s", inp.path, cfg.zones_path)

    try:
        import geopandas as gpd
        gdf = gpd.read_file(cfg.zones_path)
    except Exception as exc:
        raise ImportError(f"geopandas required for zonal_stats: {exc}")

    data, profile = _io.read_raster(inp.path, band=inp.band)
    transform = profile["transform"]
    height, width = data.shape

    rows = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        zone_id = row.get(cfg.zone_id_field, idx)
        mask = geometry_mask(
            [geom.__geo_interface__],
            transform=transform,
            invert=True,
            out_shape=(height, width),
        )
        masked_vals = data[mask]
        stats = _compute_stats(masked_vals, cfg.stats)
        entry = {cfg.zone_id_field: zone_id, **stats}
        rows.append(entry)

    out_path = cfg.output_path or (job.output.path if job.output else "zonal_stats_output.csv")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    fmt = cfg.output_format.lower()
    if fmt == "csv":
        if rows:
            with open(out_path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
    elif fmt in ("json", "geojson"):
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2, default=str)
    else:
        raise ValueError(f"Unknown output_format: {cfg.output_format}")

    log.info("[zonal_stats] ✓ %d zones → %s", len(rows), out_path)
    return out_path
