# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor — shared PDF and JSON report generation.

Generates standardised PDF summary reports and machine-readable JSON result
files for the CVG Wizard Suite output products.

Public API
----------
ReportData
    Container for all data going into a report.
build_json_report(data, path) -> Path
    Write a JSON report file.
build_pdf_report(data, path) -> Path
    Write a PDF summary report (uses reportlab if available, else text fallback).
ReportBuilder
    High-level builder that calls both JSON and PDF generation.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

log = logging.getLogger(__name__)

# Optional reportlab
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )
    _HAS_REPORTLAB = True
except ImportError:
    _HAS_REPORTLAB = False
    log.debug("reportlab not installed — PDF reports will be plain-text.")


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class ReportSection:
    """A single section within a report (heading + body paragraphs + table)."""
    heading: str
    paragraphs: List[str] = field(default_factory=list)
    table_headers: List[str] = field(default_factory=list)
    table_rows: List[List[str]] = field(default_factory=list)


@dataclass
class ReportData:
    """All data required to generate a CVG Wizard report.

    Attributes
    ----------
    title : str
        Report title (e.g. 'Storm Surge Flood Depth Analysis').
    subtitle : str
        Optional subtitle line.
    site_name : str
        Project / site name.
    generated_by : str
        Wizard name and version string.
    generated_at : str
        ISO-8601 UTC timestamp.
    inputs : dict
        Input parameter summary.
    results : dict
        Core numeric results (depths, areas, etc.).
    sections : list[ReportSection]
        Ordered content sections.
    metadata : dict
        Arbitrary extra metadata for JSON output.
    """

    title: str = "CVG GeoServ Processor — Analysis Report"
    subtitle: str = ""
    site_name: str = ""
    generated_by: str = "CVG GeoServ Processor v1.0.0"
    generated_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )
    inputs: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)
    sections: List[ReportSection] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_section(
        self,
        heading: str,
        paragraphs: Optional[List[str]] = None,
        table_headers: Optional[List[str]] = None,
        table_rows: Optional[List[List[str]]] = None,
    ) -> None:
        """Append a content section to this report."""
        self.sections.append(ReportSection(
            heading=heading,
            paragraphs=paragraphs or [],
            table_headers=table_headers or [],
            table_rows=table_rows or [],
        ))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a plain dict (sections serialised manually)."""
        d = {
            "title": self.title,
            "subtitle": self.subtitle,
            "site_name": self.site_name,
            "generated_by": self.generated_by,
            "generated_at": self.generated_at,
            "inputs": self.inputs,
            "results": self.results,
            "sections": [
                {
                    "heading": s.heading,
                    "paragraphs": s.paragraphs,
                    "table_headers": s.table_headers,
                    "table_rows": s.table_rows,
                }
                for s in self.sections
            ],
            "metadata": self.metadata,
        }
        return d


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------

def build_json_report(
    data: ReportData,
    path: Union[str, Path],
    indent: int = 2,
) -> Path:
    """Write *data* as a formatted JSON file to *path*.

    Parameters
    ----------
    data : ReportData
        Report data container.
    path : str | Path
        Output file path.
    indent : int
        JSON indentation level.

    Returns
    -------
    Path
        Absolute path of the written file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data.to_dict(), indent=indent, default=str)
    path.write_text(content, encoding="utf-8")
    log.info("JSON report written: %s", path)
    return path.resolve()


# ---------------------------------------------------------------------------
# PDF report
# ---------------------------------------------------------------------------

def build_pdf_report(
    data: ReportData,
    path: Union[str, Path],
) -> Path:
    """Write *data* as a PDF summary report to *path*.

    Uses reportlab for a formatted PDF; falls back to a plain-text .txt
    file if reportlab is not installed.

    Parameters
    ----------
    data : ReportData
        Report data container.
    path : str | Path
        Output file path (.pdf extension).

    Returns
    -------
    Path
        Absolute path of the written file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if _HAS_REPORTLAB:
        return _build_pdf_reportlab(data, path)
    else:
        txt_path = path.with_suffix(".txt")
        return _build_text_report(data, txt_path)


def _build_pdf_reportlab(data: ReportData, path: Path) -> Path:
    """Internal: generate PDF using reportlab."""
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "CVGTitle",
        parent=styles["Title"],
        fontSize=18,
        spaceAfter=6,
        textColor=colors.HexColor("#1B4F72"),
    )
    heading_style = ParagraphStyle(
        "CVGHeading",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=12,
        spaceAfter=4,
        textColor=colors.HexColor("#2E86C1"),
    )
    body_style = styles["BodyText"]
    small_style = ParagraphStyle(
        "CVGSmall",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.grey,
    )

    doc = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=1.0 * inch,
        bottomMargin=0.75 * inch,
    )

    story = []

    # --- Header ---
    story.append(Paragraph(data.title, title_style))
    if data.subtitle:
        story.append(Paragraph(data.subtitle, heading_style))
    story.append(HRFlowable(width="100%", thickness=1,
                             color=colors.HexColor("#2E86C1")))
    story.append(Spacer(1, 0.1 * inch))

    # Meta
    meta_rows = [
        ["Site", data.site_name or "—"],
        ["Generated by", data.generated_by],
        ["Generated at", data.generated_at],
    ]
    meta_table = Table(meta_rows, colWidths=[1.5 * inch, 5.0 * inch])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1B4F72")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.15 * inch))

    # --- Inputs ---
    if data.inputs:
        story.append(Paragraph("Inputs", heading_style))
        rows = [[str(k), str(v)] for k, v in data.inputs.items()]
        t = Table(rows, colWidths=[2.5 * inch, 4.0 * inch])
        t.setStyle(_kv_table_style())
        story.append(t)
        story.append(Spacer(1, 0.1 * inch))

    # --- Results ---
    if data.results:
        story.append(Paragraph("Results", heading_style))
        rows = [[str(k), str(v)] for k, v in data.results.items()]
        t = Table(rows, colWidths=[2.5 * inch, 4.0 * inch])
        t.setStyle(_kv_table_style())
        story.append(t)
        story.append(Spacer(1, 0.1 * inch))

    # --- Content sections ---
    for sec in data.sections:
        story.append(Paragraph(sec.heading, heading_style))
        for para in sec.paragraphs:
            story.append(Paragraph(para, body_style))
            story.append(Spacer(1, 0.05 * inch))
        if sec.table_headers and sec.table_rows:
            tdata = [sec.table_headers] + sec.table_rows
            col_w = (6.5 * inch) / max(len(sec.table_headers), 1)
            t = Table(tdata, colWidths=[col_w] * len(sec.table_headers))
            t.setStyle(_data_table_style())
            story.append(t)
            story.append(Spacer(1, 0.1 * inch))

    # --- Footer note ---
    story.append(Spacer(1, 0.2 * inch))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Paragraph(
        "(c) Clearview Geographic, LLC — All Rights Reserved | Est. 2018 | "
        "www.clearviewgeographic.com",
        small_style,
    ))

    doc.build(story)
    log.info("PDF report written: %s", path)
    return path.resolve()


def _build_text_report(data: ReportData, path: Path) -> Path:
    """Internal: generate plain-text report when reportlab is unavailable."""
    lines = [
        "=" * 70,
        data.title.upper(),
        data.subtitle,
        "=" * 70,
        f"Site         : {data.site_name}",
        f"Generated by : {data.generated_by}",
        f"Generated at : {data.generated_at}",
        "",
        "INPUTS",
        "-" * 40,
    ]
    for k, v in data.inputs.items():
        lines.append(f"  {k}: {v}")
    lines += ["", "RESULTS", "-" * 40]
    for k, v in data.results.items():
        lines.append(f"  {k}: {v}")
    for sec in data.sections:
        lines += ["", sec.heading.upper(), "-" * 40]
        for p in sec.paragraphs:
            lines.append(p)
        if sec.table_headers:
            lines.append("  " + " | ".join(sec.table_headers))
            for row in sec.table_rows:
                lines.append("  " + " | ".join(str(c) for c in row))
    lines += [
        "",
        "=" * 70,
        "(c) Clearview Geographic, LLC — All Rights Reserved | Est. 2018",
        "=" * 70,
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Text report written: %s", path)
    return path.resolve()


def _kv_table_style() -> TableStyle:
    return TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1B4F72")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D6EAF8")),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1),
         [colors.white, colors.HexColor("#EBF5FB")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ])


def _data_table_style() -> TableStyle:
    return TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E86C1")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#EBF5FB")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ])


# ---------------------------------------------------------------------------
# High-level builder
# ---------------------------------------------------------------------------

class ReportBuilder:
    """High-level builder that coordinates JSON + PDF report generation.

    Parameters
    ----------
    output_dir : str | Path
        Directory where reports are written.
    prefix : str
        Filename prefix (e.g. 'ssw_100yr').

    Usage
    -----
    ::

        rb = ReportBuilder("./output", "ssw_100yr")
        rb.data.title = "Storm Surge Analysis — 100-Year Event"
        rb.data.inputs["Station"] = "8720218"
        rb.data.results["Max Depth (m)"] = "2.34"
        json_path, pdf_path = rb.build()
    """

    def __init__(
        self,
        output_dir: Union[str, Path] = "./output",
        prefix: str = "cvg_report",
    ) -> None:
        self.output_dir = Path(output_dir)
        self.prefix = prefix
        self.data = ReportData()

    @property
    def json_path(self) -> Path:
        return self.output_dir / f"{self.prefix}.json"

    @property
    def pdf_path(self) -> Path:
        return self.output_dir / f"{self.prefix}.pdf"

    def build(self) -> Tuple[Path, Path]:
        """Generate JSON and PDF reports.  Returns (json_path, pdf_path)."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        j = build_json_report(self.data, self.json_path)
        p = build_pdf_report(self.data, self.pdf_path)
        return j, p
