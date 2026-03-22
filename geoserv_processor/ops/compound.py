"""Compound flood depth grid operation.

Merges multiple depth-grid inputs (surge + rainfall + SLR) into a
single combined output depth grid using the specified aggregation method.

Supported methods:
  max           — element-wise maximum (worst-case / envelope analysis)
  sum           — element-wise sum (additive combination)
  weighted_sum  — weighted sum; supply weights list in params.weights

Expected job.params keys:
  inputs    : list[str]   — input depth grid raster paths
  output    : str         — output depth grid raster path
  method    : str         — "max" | "sum" | "weighted_sum"  (default "max")
  nodata    : float       — nodata sentinel value            (default -9999.0)
  weights   : list[float] — per-input weights for weighted_sum
  resampling: str         — rasterio Resampling name for grid alignment
                            (default "bilinear")
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import numpy as np

from geoserv_processor.config import JobConfig

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_compound(job: JobConfig) -> str:
    """Merge N input depth grids into a single combined output raster.

    Returns the output file path as a string.
    Raises ValueError on missing / inconsistent configuration.
    Raises ImportError if rasterio is not installed.
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject, calculate_default_transform

    params = job.params or {}
    input_paths: List[str] = params.get("inputs", [])
    output_path: Optional[str] = params.get("output") or getattr(job, "output_path", None)
    nodata: float = float(params.get("nodata", -9999.0))
    method: str = params.get("method", "max")
    weights: Optional[List[float]] = params.get("weights")
    resampling_name: str = params.get("resampling", "bilinear")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    if not input_paths:
        raise ValueError(
            "compound op requires at least one path in params['inputs']"
        )
    if not output_path:
        raise ValueError(
            "compound op requires params['output'] or job.output_path"
        )
    if method not in {"max", "sum", "weighted_sum"}:
        raise ValueError(
            f"compound op: unknown method '{method}'. "
            "Valid values: 'max', 'sum', 'weighted_sum'."
        )
    if method == "weighted_sum":
        if weights is None:
            raise ValueError(
                "compound op: method='weighted_sum' requires params['weights'] list."
            )
        if len(weights) != len(input_paths):
            raise ValueError(
                f"compound op: weights length {len(weights)} "
                f"!= inputs length {len(input_paths)}."
            )

    try:
        resampling = Resampling[resampling_name]
    except KeyError:
        log.warning(
            "[compound] Unknown resampling '%s', falling back to bilinear.",
            resampling_name,
        )
        resampling = Resampling.bilinear

    log.info(
        "[compound] Merging %d depth grid(s) via method='%s'",
        len(input_paths),
        method,
    )

    # ------------------------------------------------------------------
    # Read reference grid (first input defines CRS / transform / shape)
    # ------------------------------------------------------------------
    arrays: List[np.ndarray] = []
    profile = None

    with rasterio.open(input_paths[0]) as ref:
        ref_crs = ref.crs
        ref_transform = ref.transform
        ref_height = ref.height
        ref_width = ref.width
        profile = ref.profile.copy()
        data = ref.read(1).astype(np.float32)
        src_nodata = ref.nodata if ref.nodata is not None else nodata
        data = np.where(data == src_nodata, np.nan, data)
        arrays.append(data)

    # ------------------------------------------------------------------
    # Read (and reproject if necessary) remaining grids onto the reference
    # ------------------------------------------------------------------
    for idx, path in enumerate(input_paths[1:], start=1):
        with rasterio.open(path) as src:
            src_nodata = src.nodata if src.nodata is not None else nodata
            if src.crs != ref_crs or src.transform != ref_transform or \
               src.height != ref_height or src.width != ref_width:
                log.debug(
                    "[compound] Reprojecting input %d to match reference grid.", idx
                )
                dest = np.empty((ref_height, ref_width), dtype=np.float32)
                reproject(
                    source=rasterio.band(src, 1),
                    destination=dest,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=ref_transform,
                    dst_crs=ref_crs,
                    resampling=resampling,
                    src_nodata=src_nodata,
                    dst_nodata=np.nan,
                )
                data = dest
            else:
                data = src.read(1).astype(np.float32)
                data = np.where(data == src_nodata, np.nan, data)
        arrays.append(data)

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------
    stack = np.stack(arrays, axis=0)  # shape: (N, height, width)

    if method == "max":
        result = np.nanmax(stack, axis=0)
    elif method == "sum":
        result = np.nansum(stack, axis=0)
    else:  # weighted_sum
        w = np.array(weights, dtype=np.float32)[:, None, None]
        result = np.nansum(stack * w, axis=0)

    # Restore nodata sentinel where all inputs were nodata (NaN)
    all_nan_mask = np.all(np.isnan(stack), axis=0)
    result = np.where(all_nan_mask, nodata, result)
    result = np.where(np.isnan(result), nodata, result)

    # ------------------------------------------------------------------
    # Write output
    # ------------------------------------------------------------------
    profile.update(
        {
            "nodata": nodata,
            "dtype": "float32",
            "count": 1,
            "compress": "lzw",
            "tiled": True,
            "blockxsize": 256,
            "blockysize": 256,
        }
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(result.astype(np.float32), 1)

    log.info("[compound] Output written: %s", output_path)
    return str(output_path)
