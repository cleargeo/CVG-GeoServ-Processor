# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor — Reclassify operation: map value ranges to new values."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from geoserv_processor import io as _io

if TYPE_CHECKING:
    from geoserv_processor.config import JobConfig

log = logging.getLogger(__name__)


def run_reclassify(job: "JobConfig") -> str:
    """Reclassify raster values based on range rules in job.reclassify."""
    inp = job.inputs[0]
    out = job.output
    cfg = job.reclassify

    if cfg is None:
        raise ValueError("Reclassify job requires a 'reclassify' config block.")
    if not cfg.rules:
        raise ValueError("Reclassify config has no rules defined.")

    log.info("[reclassify] %s → %s  (%d rules)", inp.path, out.path, len(cfg.rules))

    data, profile = _io.read_raster(inp.path, band=inp.band)
    result = np.full_like(data, cfg.default_value)

    for rule in cfg.rules:
        mask = (data >= rule.vmin) & (data < rule.vmax)
        result[mask] = rule.new_value
        log.debug("  rule [%.3f, %.3f) → %.3f  pixels=%d", rule.vmin, rule.vmax, rule.new_value, mask.sum())

    # Preserve nodata
    result[np.isnan(data)] = np.nan

    _io.write_raster(
        out.path, result, profile,
        compress=out.compress, tiled=out.tiled, tile_size=out.tile_size,
        bigtiff=out.bigtiff, nodata=out.nodata, overwrite=out.overwrite,
    )
    log.info("[reclassify] ✓ complete → %s", out.path)
    return out.path
