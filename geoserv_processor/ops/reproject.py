# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor — Reproject operation."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from geoserv_processor import io as _io

if TYPE_CHECKING:
    from geoserv_processor.config import JobConfig

log = logging.getLogger(__name__)


def run_reproject(job: "JobConfig") -> str:
    """Reproject the first input raster to the CRS defined in job.reproject."""
    import rasterio
    from rasterio.crs import CRS
    from rasterio.warp import calculate_default_transform, reproject as _warp

    inp = job.inputs[0]
    out = job.output
    cfg = job.reproject

    if cfg is None:
        raise ValueError("Reproject job requires a 'reproject' config block.")

    dst_crs = CRS.from_user_input(cfg.crs)
    resampling = _io.get_resampling(cfg.resampling)

    log.info("[reproject] %s → CRS=%s", inp.path, cfg.crs)

    with rasterio.open(inp.path) as src:
        src_crs = src.crs
        src_nodata = src.nodata if src.nodata is not None else out.nodata

        if cfg.target_resolution is not None:
            res = cfg.target_resolution
            transform, width, height = calculate_default_transform(
                src_crs, dst_crs, src.width, src.height, *src.bounds,
                resolution=res,
            )
        else:
            transform, width, height = calculate_default_transform(
                src_crs, dst_crs, src.width, src.height, *src.bounds
            )

        profile = dict(src.profile)
        profile.update(
            crs=dst_crs,
            transform=transform,
            width=width,
            height=height,
            nodata=out.nodata,
            dtype="float32",
        )

        src_data = src.read(inp.band).astype(np.float32)
        dst_data = np.full((height, width), out.nodata, dtype=np.float32)

        _warp(
            source=src_data,
            destination=dst_data,
            src_transform=src.transform,
            src_crs=src_crs,
            src_nodata=src_nodata,
            dst_transform=transform,
            dst_crs=dst_crs,
            dst_nodata=out.nodata,
            resampling=resampling,
        )

    dst_data[dst_data == out.nodata] = np.nan
    _io.write_raster(
        out.path, dst_data, profile,
        compress=out.compress, tiled=out.tiled, tile_size=out.tile_size,
        bigtiff=out.bigtiff, nodata=out.nodata, overwrite=out.overwrite,
    )
    log.info("[reproject] ✓ complete → %s  (%dx%d)", out.path, width, height)
    return out.path
