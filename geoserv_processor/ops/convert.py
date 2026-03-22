# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor — Convert operation: format/compression/COG conversion."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from geoserv_processor import io as _io

if TYPE_CHECKING:
    from geoserv_processor.config import JobConfig

log = logging.getLogger(__name__)


def run_convert(job: "JobConfig") -> str:
    """Convert raster format/compression. Optionally writes Cloud Optimized GeoTIFF."""
    import rasterio
    from pathlib import Path

    inp = job.inputs[0]
    out = job.output
    cfg = job.convert

    compress = cfg.compress if cfg else out.compress
    tiled = cfg.tiled if cfg else out.tiled
    tile_size = cfg.tile_size if cfg else out.tile_size
    bigtiff = cfg.bigtiff if cfg else out.bigtiff
    cog = cfg.cog if cfg else False

    log.info("[convert] %s → %s  compress=%s tiled=%s cog=%s", inp.path, out.path, compress, tiled, cog)

    data, profile = _io.read_raster(inp.path, band=inp.band)
    _io.write_raster(
        out.path, data, profile,
        compress=compress, tiled=tiled, tile_size=tile_size,
        bigtiff=bigtiff, nodata=out.nodata, overwrite=out.overwrite,
    )

    if cog:
        _apply_cog_overviews(out.path)

    log.info("[convert] ✓ complete → %s", out.path)
    return out.path


def _apply_cog_overviews(path: str) -> None:
    """Add internal overviews to make file Cloud Optimized (COG)."""
    import rasterio
    from rasterio.enums import Resampling
    overview_levels = [2, 4, 8, 16, 32, 64]
    with rasterio.open(path, "r+") as dst:
        dst.build_overviews(overview_levels, Resampling.average)
        dst.update_tags(ns="rio_overview", resampling="average")
    log.info("[convert] COG overviews added to %s", path)