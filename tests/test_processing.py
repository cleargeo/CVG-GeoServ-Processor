# -*- coding: utf-8 -*-
"""Tests for geoserv_processor.processing"""
import numpy as np
import pytest
from unittest.mock import MagicMock

from geoserv_processor.depth import (
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
from geoserv_processor.io import RasterData


def _make_dem(values, transform=None, crs=None):
    arr = np.array(values, dtype=np.float32)
    if transform is None:
        from affine import Affine
        transform = Affine(1.0, 0, 0, 0, -1.0, arr.shape[0])
    return RasterData(array=arr, transform=transform, crs=crs or "EPSG:4326")

class TestComputeDepthGrid:
    def test_simple(self):
        dem = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
        depth = compute_depth_grid(dem, wse=3.0)
        assert depth[0, 0] == pytest.approx(2.0)
        assert depth[0, 1] == pytest.approx(1.0)
        assert np.isnan(depth[1, 0])  # 3.0 - 3.0 = 0 -> below threshold
        assert np.isnan(depth[1, 1])  # 4.0 > 3.0 -> negative, nan

    def test_threshold(self):
        dem = np.array([[1.0, 2.9, 3.0]], dtype=np.float32)
        depth = compute_depth_grid(dem, wse=3.0, threshold_m=0.2)
        assert not np.isnan(depth[0, 0])   # 2.0 m depth > 0.2
        assert np.isnan(depth[0, 1])       # 0.1 m < threshold
        assert np.isnan(depth[0, 2])       # 0.0 m at threshold -> nan

    def test_nodata_preserved(self):
        dem = np.array([[np.nan, 1.0]], dtype=np.float32)
        depth = compute_depth_grid(dem, wse=3.0)
        assert np.isnan(depth[0, 0])
        assert depth[0, 1] == pytest.approx(2.0)

class TestInundateDem:
    def test_returns_raster_data(self):
        dem_data = _make_dem([[1.0, 2.0], [3.0, 4.0]])
        result = inundate_dem(dem_data, wse_elev_m=3.0)
        assert isinstance(result, RasterData)
        assert result.array.shape == (2, 2)


class TestComputeCompoundDepth:
    def test_max(self):
        grids = [
            _make_dem([[1.0, 2.0]]),
            _make_dem([[3.0, 0.5]]),
        ]
        result = compute_compound_depth(grids, method="max")
        assert result.array[0, 0] == pytest.approx(3.0)
        assert result.array[0, 1] == pytest.approx(2.0)

    def test_sum(self):
        grids = [
            _make_dem([[1.0, np.nan]]),
            _make_dem([[2.0, np.nan]]),
        ]
        result = compute_compound_depth(grids, method="sum")
        assert result.array[0, 0] == pytest.approx(3.0)
        assert np.isnan(result.array[0, 1])

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            compute_compound_depth([])

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError):
            compute_compound_depth([_make_dem([[1.0]])], method="bogus")

class TestBathtubFill:
    def test_simple_fill(self):
        dem = _make_dem([
            [0.0, 0.0, 5.0],
            [0.0, 0.0, 5.0],
            [5.0, 5.0, 5.0],
        ])
        wet = apply_bathtub_fill(dem, wse_m=2.0)
        # Boundary cells at 0.0 should be wet and flood inland
        assert wet[0, 0]
        assert wet[1, 1]
        assert not wet[0, 2]


class TestClassifyDepth:
    def test_classification(self):
        depth = np.array([[0.1, 0.5, 1.0, 2.0, np.nan]], dtype=np.float32)
        classes = classify_depth(depth, breaks=(0.3, 0.6, 0.9, 1.5, 3.0))
        assert classes[0, 0] == 1   # 0.1 <= 0.3
        assert classes[0, 1] == 2   # 0.3 < 0.5 <= 0.6
        assert classes[0, 3] == 5   # 1.5 < 2.0 <= 3.0  (5th class interval)
        assert classes[0, 4] == 0   # NaN -> 0

class TestPercentAreaFlooded:
    def test_all_wet(self):
        depth = np.array([[1.0, 2.0], [3.0, 4.0]])
        pct = percent_area_flooded(depth, pixel_area_m2=100.0)
        assert pct == pytest.approx(100.0)

    def test_half_wet(self):
        depth = np.array([[1.0, np.nan], [3.0, np.nan]])
        pct = percent_area_flooded(depth, pixel_area_m2=100.0)
        assert pct == pytest.approx(100.0)  # 2/2 valid cells are wet

    def test_none_wet(self):
        depth = np.full((3, 3), np.nan)
        pct = percent_area_flooded(depth, pixel_area_m2=100.0)
        assert pct == 0.0


class TestDepthStatistics:
    def test_basic(self):
        depth = np.array([[1.0, 2.0, np.nan]])
        stats = depth_statistics(depth)
        assert stats["min"] == pytest.approx(1.0)
        assert stats["max"] == pytest.approx(2.0)
        assert stats["mean"] == pytest.approx(1.5)
        assert stats["wet_cells"] == 2

    def test_all_nan(self):
        depth = np.full((3, 3), np.nan)
        stats = depth_statistics(depth)
        assert all(np.isnan(v) for k, v in stats.items() if k != "wet_cells")

class TestWseFromReturnPeriod:
    def test_exact_match(self):
        table = {10: 1.0, 100: 2.0, 500: 3.0}
        assert wse_from_return_period(100, table) == pytest.approx(2.0)

    def test_interpolation(self):
        table = {10: 1.0, 100: 2.0}
        val = wse_from_return_period(55, table)
        assert 1.0 < val < 2.0

    def test_below_min(self):
        table = {10: 1.0, 100: 2.0}
        assert wse_from_return_period(1, table) == pytest.approx(1.0)

    def test_above_max(self):
        table = {10: 1.0, 100: 2.0}
        assert wse_from_return_period(500, table) == pytest.approx(2.0)
