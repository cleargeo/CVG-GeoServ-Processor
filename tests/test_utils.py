# -*- coding: utf-8 -*-
"""Tests for geoserv_processor.utils"""
import math
import pytest
from geoserv_processor.utils import (
    ft_to_m, m_to_ft, in_to_mm, mm_to_in,
    haversine_km, validate_lat_lon, bbox_from_point,
    return_period_to_aep, aep_to_return_period,
    tr55_runoff_depth, rainfall_intensity_mm_hr,
    slugify, timestamp_str, safe_mkdir, flatten_dict, deep_merge,
    human_bytes, unique_path,
)


class TestUnitConversions:
    def test_ft_to_m(self):
        assert ft_to_m(1.0) == pytest.approx(0.3048)
        assert ft_to_m(0.0) == 0.0

    def test_m_to_ft_roundtrip(self):
        for v in [0.5, 1.0, 10.0, 100.0]:
            assert m_to_ft(ft_to_m(v)) == pytest.approx(v, rel=1e-6)

    def test_in_to_mm(self):
        assert in_to_mm(1.0) == pytest.approx(25.4)

    def test_mm_to_in_roundtrip(self):
        assert mm_to_in(in_to_mm(5.0)) == pytest.approx(5.0)

class TestCoordinateUtils:
    def test_haversine_same_point(self):
        assert haversine_km(29.65, -81.63, 29.65, -81.63) == pytest.approx(0.0, abs=1e-6)

    def test_haversine_known(self):
        # Jacksonville to Key West is roughly 530 km
        d = haversine_km(30.33, -81.66, 24.56, -81.81)
        assert 500 < d < 700

    def test_validate_lat_lon_ok(self):
        validate_lat_lon(29.65, -81.63)  # should not raise

    def test_validate_lat_out_of_range(self):
        with pytest.raises(ValueError):
            validate_lat_lon(91.0, 0.0)

    def test_validate_lon_out_of_range(self):
        with pytest.raises(ValueError):
            validate_lat_lon(0.0, 181.0)

    def test_bbox_from_point(self):
        w, s, e, n = bbox_from_point(29.65, -81.63, radius_km=10.0)
        assert w < -81.63 < e
        assert s < 29.65 < n

class TestHydrologyHelpers:
    def test_return_period_to_aep(self):
        assert return_period_to_aep(100) == pytest.approx(0.01)
        assert return_period_to_aep(2) == pytest.approx(0.5)

    def test_return_period_zero_raises(self):
        with pytest.raises(ValueError):
            return_period_to_aep(0)

    def test_aep_to_return_period(self):
        assert aep_to_return_period(0.01) == pytest.approx(100.0)

    def test_aep_roundtrip(self):
        for rp in [2, 10, 100, 500]:
            assert aep_to_return_period(return_period_to_aep(rp)) == pytest.approx(rp)

    def test_tr55_no_runoff_below_ia(self):
        # CN=75 -> S=8.33 in -> Ia=1.67 in -> 42.4 mm - below that, Q=0
        Q = tr55_runoff_depth(10.0, curve_number=75)
        assert Q == 0.0

    def test_tr55_runoff_positive(self):
        Q = tr55_runoff_depth(100.0, curve_number=85)
        assert Q > 0

    def test_tr55_bad_cn_raises(self):
        with pytest.raises(ValueError):
            tr55_runoff_depth(100.0, curve_number=0)

    def test_rainfall_intensity(self):
        assert rainfall_intensity_mm_hr(120.0, 24.0) == pytest.approx(5.0)

class TestStringUtils:
    def test_slugify_basic(self):
        assert slugify("Hello World") == "hello_world"

    def test_slugify_special(self):
        assert slugify("100-Year Flood Depth (NAVD88)") == "100_year_flood_depth_navd88"

    def test_timestamp_str_format(self):
        ts = timestamp_str("%Y%m%d")
        assert len(ts) == 8
        assert ts.isdigit()

    def test_human_bytes(self):
        assert "KB" in human_bytes(2048)
        assert "MB" in human_bytes(2_000_000)


class TestFileUtils:
    def test_safe_mkdir(self, tmp_path):
        p = safe_mkdir(tmp_path / "a" / "b" / "c")
        assert p.exists()
        assert p.is_dir()

    def test_unique_path_no_collision(self, tmp_path):
        p = unique_path(tmp_path / "nonexistent.tif")
        assert p.name == "nonexistent.tif"

    def test_unique_path_collision(self, tmp_path):
        existing = tmp_path / "output.tif"
        existing.write_bytes(b"")
        p = unique_path(existing)
        assert p.name == "output_1.tif"

class TestDictUtils:
    def test_flatten_dict(self):
        d = {"a": {"b": 1, "c": 2}, "d": 3}
        flat = flatten_dict(d)
        assert flat == {"a.b": 1, "a.c": 2, "d": 3}

    def test_deep_merge(self):
        base = {"a": 1, "b": {"x": 10, "y": 20}}
        override = {"b": {"y": 99, "z": 30}, "c": 3}
        result = deep_merge(base, override)
        assert result["a"] == 1
        assert result["b"]["x"] == 10
        assert result["b"]["y"] == 99
        assert result["b"]["z"] == 30
        assert result["c"] == 3
