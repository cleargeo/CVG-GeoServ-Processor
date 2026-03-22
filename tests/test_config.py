# -*- coding: utf-8 -*-
"""Tests for geoserv_processor.config"""
import json
import pytest
from geoserv_processor.config import (
    RasterInput, VectorInput, NoaaConfig,
    ProcessingConfig, OutputConfig, WizardOutputConfig, BaseWizardConfig,
)


class TestRasterInput:
    def test_basic(self):
        r = RasterInput(path="dem.tif")
        assert r.path == "dem.tif"
        assert r.band == 1
        assert r.nodata is None

    def test_empty_path_raises(self):
        with pytest.raises(ValueError):
            RasterInput(path="")

    def test_band_zero_raises(self):
        with pytest.raises(ValueError):
            RasterInput(path="dem.tif", band=0)


class TestVectorInput:
    def test_basic(self):
        v = VectorInput(path="aoi.shp")
        assert v.path == "aoi.shp"
        assert v.layer is None

    def test_empty_path_raises(self):
        with pytest.raises(ValueError):
            VectorInput(path="")

class TestProcessingConfig:
    def test_defaults(self):
        p = ProcessingConfig()
        assert p.target_crs == "EPSG:4326"
        assert p.target_resolution_m == 10.0
        assert p.max_workers == 4

    def test_custom(self):
        p = ProcessingConfig(target_resolution_m=5.0, max_workers=8)
        assert p.target_resolution_m == 5.0
        assert p.max_workers == 8


class TestOutputConfig:
    """Tests for WizardOutputConfig (wizard-level output settings)."""

    def test_defaults(self):
        o = WizardOutputConfig()
        assert o.write_geotiff is True
        assert o.prefix == "cvg"

    def test_resolved_dir_creates_path(self, tmp_path):
        o = WizardOutputConfig(output_dir=str(tmp_path / "out"))
        p = o.resolved_dir()
        assert p.exists()

    def test_op_output_config_defaults(self):
        """OutputConfig (op-level) uses path/nodata/compress fields."""
        from geoserv_processor.config import OutputConfig as OpOutputConfig
        o = OpOutputConfig()
        assert o.path == ""
        assert o.compress == "lzw"
        assert o.tiled is True

class TestBaseWizardConfig:
    def test_defaults(self):
        c = BaseWizardConfig()
        assert c.wizard_name == "CVG GeoServ Processor"

    def test_validate_ok(self):
        c = BaseWizardConfig()
        assert c.validate() == []

    def test_validate_bad_resolution(self):
        c = BaseWizardConfig()
        c.processing.target_resolution_m = -1
        errors = c.validate()
        assert any("resolution" in e for e in errors)

    def test_to_json_roundtrip(self, tmp_path):
        c = BaseWizardConfig(site_name="Test Site")
        path = str(tmp_path / "config.json")
        c.to_json(path)
        import json
        data = json.loads(open(path).read())
        assert data["site_name"] == "Test Site"
