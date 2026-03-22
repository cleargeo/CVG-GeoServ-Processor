# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# Protected under US and International copyright, trade secret,
# trademark, cybersecurity, and intellectual property law.
# This Product is developed under CVG's Agentic Development Framework (ADF).
# Unauthorized use, replication, or modification is strictly prohibited.
# -----------------------------------------------------------------------------
# Author      : Alex Zelenski, GISP
# Organization: Clearview Geographic, LLC
# Contact     : azelenski@clearviewgeographic.com  |  386-957-2314
#               contact@clearviewgeographic.com (org)
# GitHub      : azelenski_cvg | clearview-geographic (Enterprise) | cleargeo (Public)
# Website     : https://www.clearviewgeographic.com
# License     : Proprietary -- CVG-ADF | See Software-Disclaimer-License-Header.md
# =============================================================================
"""CVG GeoServ Processor -- Shared Geospatial Processing Engine.

Copyright Clearview Geographic, LLC -- All Rights Reserved | Est. 2018
Proprietary Software -- Internal Use Only

This package provides the shared geospatial processing core used by the CVG
Wizard Suite (Rainfall Wizard, SLR Wizard, Storm Surge Wizard).

Key Modules
-----------
geoserv_processor.io
    Raster and vector I/O utilities (rasterio, fiona, shapely).
geoserv_processor.processing
    DEM-based flood depth grid computation and raster algebra.
geoserv_processor.noaa
    NOAA CO-OPS and PFDS API clients for water-level and rainfall data.
geoserv_processor.config
    Base configuration dataclasses shared across all wizards.
geoserv_processor.monitoring
    Performance monitoring, timing, and resource tracking.
geoserv_processor.report
    PDF/JSON report generation utilities.
geoserv_processor.insights
    Knowledge-base semantic search for hazard guidance.
geoserv_processor.web
    Shared Flask web application factory and route helpers.
geoserv_processor.cli
    Shared CLI argument parsing and wizard interaction utilities.
geoserv_processor.utils
    Coordinate helpers, unit conversion, and miscellaneous utilities.
"""

from __future__ import annotations

try:
    from importlib.metadata import version as _pkg_version
    __version__: str = _pkg_version("geoserv-processor")
except Exception:
    __version__ = "1.0.0"

# -- Public API imports -------------------------------------------------------
from geoserv_processor.config import (  # noqa: E402
    GeoServConfig,
    JobConfig,
    InputRasterConfig,
    OutputConfig,
    ClipConfig,
    ReprojectConfig,
    MosaicConfig,
    ReclassifyConfig,
    ReclassifyRule,
    ZonalStatsConfig,
    ContourConfig,
    ConvertConfig,
    CompoundConfig,
    VALID_OPS,
)
from geoserv_processor.processing import run_geoserv_job  # noqa: E402
from geoserv_processor.io import RasterData  # noqa: E402
from geoserv_processor.depth import (  # noqa: E402
    compute_depth_grid,
    inundate_dem,
    compute_compound_depth,
    apply_bathtub_fill,
    compute_freeboard,
    classify_depth,
    percent_area_flooded,
    depth_statistics,
    wse_from_return_period,
)

__all__ = [
    # version
    "__version__",
    # config dataclasses
    "GeoServConfig",
    "JobConfig",
    "InputRasterConfig",
    "OutputConfig",
    "ClipConfig",
    "ReprojectConfig",
    "MosaicConfig",
    "ReclassifyConfig",
    "ReclassifyRule",
    "ZonalStatsConfig",
    "ContourConfig",
    "ConvertConfig",
    "CompoundConfig",
    "VALID_OPS",
    # processing / job engine
    "run_geoserv_job",
    # I/O container
    "RasterData",
    # depth / hydrology functions
    "compute_depth_grid",
    "inundate_dem",
    "compute_compound_depth",
    "apply_bathtub_fill",
    "compute_freeboard",
    "classify_depth",
    "percent_area_flooded",
    "depth_statistics",
    "wse_from_return_period",
]
