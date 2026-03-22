# -*- coding: utf-8 -*-
"""Tests for geoserv_processor.report"""
import json
import pytest
from geoserv_processor.report import (
    ReportSection, ReportData, build_json_report,
    build_pdf_report, ReportBuilder,
)


class TestReportData:
    def test_defaults(self):
        d = ReportData()
        assert d.title == "CVG GeoServ Processor — Analysis Report"
        assert d.inputs == {}
        assert d.results == {}

    def test_add_section(self):
        d = ReportData()
        d.add_section("My Section", paragraphs=["Para 1"], table_headers=["A", "B"])
        assert len(d.sections) == 1
        assert d.sections[0].heading == "My Section"

    def test_to_dict(self):
        d = ReportData(title="Test", site_name="Site A")
        dd = d.to_dict()
        assert dd["title"] == "Test"
        assert dd["site_name"] == "Site A"
        assert "sections" in dd

class TestBuildJsonReport:
    def test_writes_file(self, tmp_path):
        data = ReportData(title="JSON Test")
        data.inputs["lat"] = 29.65
        data.results["max_depth_m"] = 2.5
        path = tmp_path / "report.json"
        out = build_json_report(data, path)
        assert out.exists()
        content = json.loads(out.read_text())
        assert content["title"] == "JSON Test"
        assert content["inputs"]["lat"] == 29.65

    def test_creates_parent_dirs(self, tmp_path):
        data = ReportData()
        path = tmp_path / "sub" / "dir" / "report.json"
        out = build_json_report(data, path)
        assert out.exists()


class TestBuildPdfReport:
    def test_writes_file_or_txt(self, tmp_path):
        data = ReportData(title="PDF Test", site_name="Test Site")
        data.inputs["Station"] = "8724580"
        data.results["Depth"] = "2.5 m"
        data.add_section(
            "Summary",
            paragraphs=["Analysis complete."],
            table_headers=["RP", "Depth"],
            table_rows=[["100yr", "2.5 m"]],
        )
        path = tmp_path / "report.pdf"
        out = build_pdf_report(data, path)
        assert out.exists()
        # Either the PDF or the text fallback
        assert out.suffix in (".pdf", ".txt")

class TestReportBuilder:
    def test_build_creates_files(self, tmp_path):
        rb = ReportBuilder(output_dir=str(tmp_path), prefix="test_report")
        rb.data.title = "Builder Test"
        rb.data.inputs["key"] = "value"
        rb.data.results["result"] = "42"
        json_path, pdf_path = rb.build()
        assert json_path.exists()
        assert pdf_path.exists() or pdf_path.with_suffix(".txt").exists()

    def test_json_content(self, tmp_path):
        rb = ReportBuilder(output_dir=str(tmp_path), prefix="test")
        rb.data.title = "My Report"
        rb.data.results["depth"] = "3.1 m"
        j, _ = rb.build()
        content = json.loads(j.read_text())
        assert content["title"] == "My Report"
        assert content["results"]["depth"] == "3.1 m"
