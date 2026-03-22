# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor — Clip operation: mask raster to an AOI polygon."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from geoserv_processor import io as _io

if TYPE_CHECKING:
    from geoserv_processor.config import JobConfig

log = logging.getLogger(__name__)


def run_clip(job: "JobConfig") -> str:
    """Clip the first input raster to the AOI defined in job.clip.

    Returns the output path on success.
    """
    import rasterio
    import rasterio.mask as _rio_mask

    inp = job.inputs[0]
    out = job.output
    cfg = job.clip

    if cfg is None:
        raise ValueError("Clip job requires a 'clip' config block.")

    log.info("[clip] Loading AOI...")
    geoms = _io.load_aoi(aoi_path=cfg.aoi_path, aoi_geojson=cfg.aoi_geojson)

    log.info("[clip] %s → %s", inp.path, out.path)
    with rasterio.open(inp.path) as src:
        masked, transform = _rio_mask.mask(
            src,
            geoms,
            crop=cfg.crop,
            all_touched=cfg.all_touched,
            nodata=out.nodata,
        )
        profile = dict(src.profile)
        profile.update(
            transform=transform,
            height=masked.shape[1],
            width=masked.shape[2],
        )

    data = masked[0].astype(np.float32)
    data[data == out.nodata] = np.nan
    _io.write_raster(
        out.path, data, profile,
        compress=out.compress, tiled=out.tiled, tile_size=out.tile_size,
        bigtiff=out.bigtiff, nodata=out.nodata, overwrite=out.overwrite,
    )
    log.info("[clip] ✓ complete → %s", out.path)
    return out.path
