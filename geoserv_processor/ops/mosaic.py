# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor — Mosaic operation: merge multiple rasters."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from geoserv_processor import io as _io

if TYPE_CHECKING:
    from geoserv_processor.config import JobConfig

log = logging.getLogger(__name__)


def run_mosaic(job: "JobConfig") -> str:
    """Merge all input rasters into a single mosaic output."""
    import rasterio
    from rasterio.merge import merge as _merge

    out = job.output
    cfg = job.mosaic

    if len(job.inputs) < 2:
        raise ValueError("Mosaic job requires at least 2 inputs.")

    log.info("[mosaic] Merging %d rasters...", len(job.inputs))

    # MosaicConfig.resampling is a merge strategy string ('first', 'last', 'min', 'max', 'sum'),
    # NOT a warp resampling method — pass it directly to merge(method=...).
    src_files = [rasterio.open(inp.path) for inp in job.inputs]
    try:
        method = (cfg.resampling if cfg else "first") or "first"
        merged, transform = _merge(src_files, method=method)
        profile = dict(src_files[0].profile)
        profile.update(
            transform=transform,
            height=merged.shape[1],
            width=merged.shape[2],
            count=1,
            dtype="float32",
            nodata=out.nodata,
        )
    finally:
        for s in src_files:
            s.close()

    data = merged[0].astype(np.float32)
    data[data == out.nodata] = np.nan
    _io.write_raster(
        out.path, data, profile,
        compress=out.compress, tiled=out.tiled, tile_size=out.tile_size,
        bigtiff=out.bigtiff, nodata=out.nodata, overwrite=out.overwrite,
    )
    log.info("[mosaic] ✓ complete → %s  (%dx%d)", out.path, merged.shape[2], merged.shape[1])
    return out.path
