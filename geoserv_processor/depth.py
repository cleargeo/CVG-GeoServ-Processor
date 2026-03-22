# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor -- Hydrological depth-grid computation utilities.

Pure-NumPy functions for DEM-based flood-depth calculations.  These are the
core scientific routines shared across CVG Rainfall Wizard, SLR Wizard, and
Storm Surge Wizard.

Functions
---------
compute_depth_grid      -- depth = WSE - DEM, masked below threshold
inundate_dem            -- wrap compute_depth_grid returning a RasterData
compute_compound_depth  -- combine multiple depth grids (max / sum / mean)
apply_bathtub_fill      -- simple wet/dry mask (DEM < WSE)
compute_freeboard       -- elevation above flood surface
classify_depth          -- bin depth values into integer risk classes
percent_area_flooded    -- fraction (%) of valid pixels that are wet
depth_statistics        -- descriptive stats for a depth grid
wse_from_return_period  -- lookup / interpolate WSE from a frequency table
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from geoserv_processor.io import RasterData


# ---------------------------------------------------------------------------
# Core depth grid
# ---------------------------------------------------------------------------

def compute_depth_grid(
    dem: np.ndarray,
    wse: float,
    threshold_m: float = 0.0,
) -> np.ndarray:
    """Compute a water-depth grid from a DEM array and a scalar WSE.

    Parameters
    ----------
    dem : np.ndarray
        Bare-earth elevation array (float32 or float64).  NaN = nodata.
    wse : float
        Water surface elevation in the same vertical units as *dem*.
    threshold_m : float
        Minimum depth to retain as "flooded".  Pixels with depth <=
        *threshold_m* are set to NaN (not flooded).

    Returns
    -------
    np.ndarray (float32)
        Depth grid.  Flooded pixels contain a positive depth value;
        non-flooded pixels (below WSE or DEM nodata) are NaN.
    """
    depth = (wse - dem).astype(np.float32)
    depth[depth <= threshold_m] = np.nan
    return depth


# ---------------------------------------------------------------------------
# RasterData wrapper
# ---------------------------------------------------------------------------

def inundate_dem(dem_data: RasterData, wse_elev_m: float) -> RasterData:
    """Inundate a DEM RasterData by a scalar WSE and return a depth RasterData.

    Parameters
    ----------
    dem_data : RasterData
        Input DEM.  ``dem_data.array`` must be float32/float64.
    wse_elev_m : float
        Water surface elevation in the same units as the DEM.

    Returns
    -------
    RasterData
        Depth grid with the same spatial reference as *dem_data*.
    """
    depth_arr = compute_depth_grid(dem_data.array, wse_elev_m)
    return RasterData(array=depth_arr, transform=dem_data.transform, crs=dem_data.crs)


# ---------------------------------------------------------------------------
# Compound depth
# ---------------------------------------------------------------------------

def compute_compound_depth(
    grids: List[RasterData],
    method: str = "max",
) -> RasterData:
    """Combine multiple depth grids into a single compound hazard depth raster.

    Parameters
    ----------
    grids : list of RasterData
        Input depth grids -- must share the same shape and CRS.
    method : str
        Aggregation method: ``'max'``, ``'sum'``, or ``'mean'``.

    Returns
    -------
    RasterData
        Compound depth grid with the spatial reference of *grids[0]*.

    Raises
    ------
    ValueError
        If *grids* is empty or *method* is unknown.
    """
    if not grids:
        raise ValueError("grids must not be empty.")

    arrays = np.stack([g.array for g in grids], axis=0).astype(np.float32)
    all_nan = np.all(np.isnan(arrays), axis=0)

    if method == "max":
        result = np.nanmax(arrays, axis=0)
    elif method == "sum":
        result = np.nansum(arrays, axis=0)
    elif method == "mean":
        result = np.nanmean(arrays, axis=0)
    else:
        raise ValueError(
            f"Unknown compound method '{method}'.  Use 'max', 'sum', or 'mean'."
        )

    # Restore NaN where ALL input cells were NaN (nanmax/nansum makes them 0)
    result[all_nan] = np.nan
    return RasterData(
        array=result.astype(np.float32),
        transform=grids[0].transform,
        crs=grids[0].crs,
    )


# ---------------------------------------------------------------------------
# Bathtub fill
# ---------------------------------------------------------------------------

def apply_bathtub_fill(dem: RasterData, wse_m: float) -> np.ndarray:
    """Return a boolean wet/dry mask using the bathtub (static inundation) method.

    A pixel is considered *wet* when its elevation is below the given water
    surface elevation.  This is the simplest possible inundation model -- it
    ignores hydrological connectivity.

    Parameters
    ----------
    dem : RasterData
        Input DEM.
    wse_m : float
        Water surface elevation in the same vertical units as the DEM.

    Returns
    -------
    np.ndarray[bool]
        Boolean array; ``True`` = wet, ``False`` = dry.
    """
    return dem.array < wse_m


# ---------------------------------------------------------------------------
# Freeboard
# ---------------------------------------------------------------------------

def compute_freeboard(dem: RasterData, wse_m: float) -> np.ndarray:
    """Return freeboard = DEM elevation minus flood WSE.

    Positive values indicate the ground is *above* the flood surface (safe);
    negative values indicate the ground is *below* it (flooded).

    Parameters
    ----------
    dem : RasterData
    wse_m : float

    Returns
    -------
    np.ndarray (float32)
    """
    return (dem.array - wse_m).astype(np.float32)


# ---------------------------------------------------------------------------
# Depth classification
# ---------------------------------------------------------------------------

def classify_depth(
    depth: np.ndarray,
    breaks: Sequence[float],
) -> np.ndarray:
    """Classify a depth grid into integer risk classes defined by *breaks*.

    Each break defines the **upper bound** (inclusive) of a class.  The first
    class (class 1) covers the range ``(0, breaks[0]]``; class *k* covers
    ``(breaks[k-2], breaks[k-1]]``; values above the last break receive the
    highest class.  NaN pixels are assigned class 0.

    Parameters
    ----------
    depth : np.ndarray
        Depth grid (NaN = nodata / not flooded).
    breaks : sequence of float
        Ordered upper-bound thresholds.  E.g. ``(0.3, 0.6, 0.9, 1.5, 3.0)``
        creates 5 classes.

    Returns
    -------
    np.ndarray[int32]
        Integer class array; 0 = NaN / not classified.
    """
    classes = np.zeros(depth.shape, dtype=np.int32)
    breaks_arr = np.asarray(breaks, dtype=np.float64)
    valid = ~np.isnan(depth)

    for cls_idx in range(len(breaks_arr)):
        lower = breaks_arr[cls_idx - 1] if cls_idx > 0 else -np.inf
        upper = breaks_arr[cls_idx]
        mask = valid & (depth > lower) & (depth <= upper)
        classes[mask] = cls_idx + 1

    # Values above the last break also get the highest class
    above = valid & (depth > breaks_arr[-1])
    classes[above] = len(breaks_arr)

    return classes


# ---------------------------------------------------------------------------
# Area and statistics helpers
# ---------------------------------------------------------------------------

def percent_area_flooded(
    depth: np.ndarray,
    pixel_area_m2: float = 1.0,
) -> float:
    """Return the percentage of *valid* (non-NaN) pixels that are flooded.

    In a depth grid, non-NaN pixels by definition represent flooded cells.
    This function returns the fraction of valid cells relative to all valid
    cells -- i.e., 100 % if any valid pixels exist, 0 % if none do.

    Parameters
    ----------
    depth : np.ndarray
        Depth grid.  NaN = not flooded / nodata.
    pixel_area_m2 : float
        Individual pixel area in square metres (used by callers that need
        absolute flooded area; not used in the percentage calculation).

    Returns
    -------
    float
        Percentage in range [0, 100].
    """
    valid = ~np.isnan(depth)
    n_valid = int(np.sum(valid))
    if n_valid == 0:
        return 0.0
    n_wet = int(np.sum(valid & (depth > 0)))
    return (n_wet / n_valid) * 100.0


def depth_statistics(depth: np.ndarray) -> Dict[str, float]:
    """Compute descriptive statistics for a depth grid.

    Parameters
    ----------
    depth : np.ndarray
        Depth grid (float32 / float64).  NaN = nodata.

    Returns
    -------
    dict with keys: ``min``, ``max``, ``mean``, ``std``, ``wet_cells``.
    All float values are NaN when the grid contains no valid pixels.
    ``wet_cells`` is an integer (0 for all-NaN grids).
    """
    valid = depth[~np.isnan(depth)]
    if valid.size == 0:
        return {
            "min": float("nan"),
            "max": float("nan"),
            "mean": float("nan"),
            "std": float("nan"),
            "wet_cells": 0,
        }
    return {
        "min": float(np.min(valid)),
        "max": float(np.max(valid)),
        "mean": float(np.mean(valid)),
        "std": float(np.std(valid)),
        "wet_cells": int(valid.size),
    }


# ---------------------------------------------------------------------------
# Return-period WSE lookup
# ---------------------------------------------------------------------------

def wse_from_return_period(
    return_period: float,
    table: Dict[int, float],
) -> float:
    """Interpolate (or clamp) a WSE from a return-period frequency table.

    Parameters
    ----------
    return_period : float
        Return period in years (e.g. 100 for the 1-in-100 event).
    table : dict
        Mapping of ``{return_period_years: wse_m}`` pairs, e.g.
        ``{10: 1.0, 100: 2.0, 500: 3.0}``.

    Returns
    -------
    float
        Interpolated WSE.  Clamped to the table's min/max if *return_period*
        is outside the tabulated range.
    """
    periods = sorted(table.keys())
    if return_period <= periods[0]:
        return float(table[periods[0]])
    if return_period >= periods[-1]:
        return float(table[periods[-1]])

    # Linear interpolation between bracketing periods
    for i in range(len(periods) - 1):
        lo, hi = periods[i], periods[i + 1]
        if lo <= return_period <= hi:
            t = (return_period - lo) / (hi - lo)
            return float(table[lo] + t * (table[hi] - table[lo]))

    return float(table[periods[-1]])
