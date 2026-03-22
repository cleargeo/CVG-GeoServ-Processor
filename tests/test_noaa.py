# -*- coding: utf-8 -*-
"""Tests for geoserv_processor.noaa (offline / unit tests only)."""
import pytest
from geoserv_processor.noaa import (
    TR083_SCENARIOS,
    get_slr_projection,
    nearest_slr_station,
    NoaaCoOpsClient,
)


class TestTR083Scenarios:
    def test_all_six_scenarios_present(self):
        expected = {"low", "intermediate_low", "intermediate",
                    "intermediate_high", "high", "extreme"}
        assert set(TR083_SCENARIOS.keys()) == expected

    def test_scenario_fields(self):
        for name, scen in TR083_SCENARIOS.items():
            assert "global_2050" in scen
            assert "global_2100" in scen
            assert scen["global_2100"] > scen["global_2050"]

class TestGetSlrProjection:
    def test_baseline_is_zero(self):
        # At baseline year (1992) there should be 0 rise
        slr = get_slr_projection("8724580", "intermediate", 1992)
        assert slr == pytest.approx(0.0, abs=1e-4)

    def test_increases_with_year(self):
        slr_2050 = get_slr_projection("8724580", "intermediate", 2050)
        slr_2075 = get_slr_projection("8724580", "intermediate", 2075)
        slr_2100 = get_slr_projection("8724580", "intermediate", 2100)
        assert slr_2050 < slr_2075 < slr_2100

    def test_higher_scenario_higher_slr(self):
        low = get_slr_projection("8724580", "low", 2100)
        high = get_slr_projection("8724580", "high", 2100)
        extreme = get_slr_projection("8724580", "extreme", 2100)
        assert low < high < extreme

    def test_high_subsidence_station(self):
        # Grand Isle (8761724) has high subsidence - should exceed Key West
        kw = get_slr_projection("8724580", "intermediate", 2100)
        gi = get_slr_projection("8761724", "intermediate", 2100)
        assert gi > kw

    def test_unknown_scenario_raises(self):
        with pytest.raises(ValueError, match="Unknown SLR scenario"):
            get_slr_projection("8724580", "bogus_scenario", 2050)

class TestNearestSlrStation:
    def test_key_west_returns_key_west(self):
        # Coordinates very close to Key West
        station = nearest_slr_station(24.5597, -81.8072)
        assert station == "8724580"

    def test_norfolk_returns_norfolk(self):
        # Coordinates very close to Norfolk, VA
        station = nearest_slr_station(36.9467, -76.3300)
        assert station == "8638610"

    def test_returns_string(self):
        station = nearest_slr_station(29.65, -81.63)
        assert isinstance(station, str)
        assert len(station) == 7


class TestNoaaCoOpsClient:
    def test_init(self):
        client = NoaaCoOpsClient("8724580")
        assert client.station_id == "8724580"
        assert client.datum == "NAVD"
        assert client.units == "metric"

    def test_get_slr(self):
        client = NoaaCoOpsClient("8724580")
        slr = client.get_slr("intermediate", 2050)
        assert slr > 0

    def test_repr(self):
        client = NoaaCoOpsClient("8724580", datum="MLLW")
        r = repr(client)
        assert "8724580" in r
        assert "MLLW" in r
