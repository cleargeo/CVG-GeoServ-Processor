# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor — shared knowledge-base search and hazard guidance.

Provides keyword-based and semantic similarity search over a built-in
knowledge base of flood hazard guidance, FEMA/NOAA references, and
GIS best practices.

Public API
----------
KnowledgeEntry
    A single knowledge-base entry (question/answer/tags/source).
KNOWLEDGE_BASE : list[KnowledgeEntry]
    Built-in CVG flood hazard knowledge entries.
search_knowledge(query, top_k, min_score) -> list[KnowledgeEntry]
    Return the top-k most relevant entries for a free-text query.
format_insights(entries) -> str
    Format a list of entries as a human-readable string.
InsightsEngine
    Class wrapper with persistent query history.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Knowledge entry
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeEntry:
    """A single entry in the CVG hazard knowledge base."""

    question: str
    """The question or topic this entry addresses."""

    answer: str
    """The guidance / answer text."""

    tags: List[str] = field(default_factory=list)
    """Keywords for retrieval (lower-case)."""

    source: str = ""
    """Authoritative source (e.g. 'FEMA P-646', 'NOAA Atlas 14')."""

    score: float = 0.0
    """Relevance score (populated during search, not stored in base data)."""


# ---------------------------------------------------------------------------
# Built-in knowledge base
# ---------------------------------------------------------------------------

KNOWLEDGE_BASE: List[KnowledgeEntry] = [
    KnowledgeEntry(
        question="What is a 100-year flood?",
        answer=(
            "A 100-year flood (also called the 1% Annual Chance Flood or 1%-AEP flood) "
            "is a flood event with a 1 percent probability of being equalled or exceeded "
            "in any given year. It does not mean the flood occurs only once every 100 years. "
            "FEMA uses this standard to define the Special Flood Hazard Area (SFHA) on "
            "Flood Insurance Rate Maps (FIRMs)."
        ),
        tags=["100-year", "return period", "aep", "fema", "sfha", "firm"],
        source="FEMA FIRM / 44 CFR Part 65",
    ),
    KnowledgeEntry(
        question="What is NAVD88 and why does it matter for flood mapping?",
        answer=(
            "NAVD88 (North American Vertical Datum of 1988) is the standard vertical "
            "datum used by FEMA for flood mapping in the contiguous United States. "
            "All flood elevations on modern FIRMs are referenced to NAVD88. When "
            "processing DEMs and water-surface elevations, ensure all data are "
            "co-registered to NAVD88 to avoid datum-shift errors that can reach "
            "0.5–1.5 m in coastal areas."
        ),
        tags=["navd88", "datum", "vertical datum", "dem", "elevation", "fema", "firm"],
        source="NOAA NGS / FEMA FIRM Technical Reference",
    ),
    KnowledgeEntry(
        question="What is sea-level rise and which NOAA scenarios should I use?",
        answer=(
            "Sea-level rise (SLR) is the long-term increase in mean sea level relative "
            "to land. NOAA Technical Report NOS CO-OPS 083 defines six scenarios: "
            "Low (0.3 m), Intermediate-Low (0.5 m), Intermediate (1.0 m), "
            "Intermediate-High (1.5 m), High (2.0 m), and Extreme (2.5 m) by 2100 "
            "relative to 1992. For infrastructure with a 50-year design life, "
            "Intermediate or Intermediate-High is typically recommended. "
            "Local subsidence (e.g. ground settlement) must be added separately."
        ),
        tags=["slr", "sea level rise", "noaa", "tr-083", "scenario",
              "intermediate", "high", "projection", "2100"],
        source="NOAA TR NOS CO-OPS 083 (2022)",
    ),
    KnowledgeEntry(
        question="How does storm surge differ from tidal flooding?",
        answer=(
            "Storm surge is the abnormal rise in seawater level during a storm, "
            "driven primarily by wind stress and low atmospheric pressure. Tidal "
            "flooding (also called nuisance flooding or sunny-day flooding) is caused "
            "by astronomical tides exceeding the local high-water threshold. Storm surge "
            "can reach 5–10 m during major hurricanes; tidal flooding typically involves "
            "< 0.5 m above MHHW. Compound flooding occurs when storm surge coincides "
            "with rainfall and/or high tides."
        ),
        tags=["storm surge", "tidal flooding", "hurricane", "compound flood",
              "mhhw", "surge", "wind"],
        source="NOAA NWS / FEMA Coastal Flood Guidance",
    ),
    KnowledgeEntry(
        question="What is a Digital Elevation Model (DEM) and what resolution is appropriate?",
        answer=(
            "A DEM is a raster grid where each cell stores the ground surface elevation. "
            "For coastal flood mapping, 1/3 arc-second (~10 m) or 1/9 arc-second (~3 m) "
            "USGS 3DEP data are commonly used. For detailed site studies, LiDAR-derived "
            "DEMs at 1 m resolution are preferred. Higher resolution improves depth-grid "
            "accuracy but significantly increases processing time. Always verify the "
            "vertical accuracy (RMSE) meets project requirements — USGS 3DEP targets "
            "± 0.1 m RMSE at the 95% confidence level."
        ),
        tags=["dem", "digital elevation model", "lidar", "3dep", "resolution",
              "usgs", "raster", "accuracy"],
        source="USGS 3DEP / FEMA MAP Program",
    ),
    KnowledgeEntry(
        question="What is compound flooding?",
        answer=(
            "Compound flooding occurs when two or more flood drivers act simultaneously "
            "or in close succession, producing impacts greater than either driver alone. "
            "Common combinations include: storm surge + rainfall runoff, coastal tide + "
            "riverine flood, and sea-level rise + storm surge. CVG Wizard Suite supports "
            "compound analysis by merging depth grids from separate hazard runs using "
            "maximum, sum, or mean combination methods."
        ),
        tags=["compound flood", "compound", "surge", "rainfall", "runoff", "slr",
              "combination", "concurrent"],
        source="FEMA / USACE / NOAA Compound Flood Guidance",
    ),
    KnowledgeEntry(
        question="What Curve Number (CN) should I use for NRCS TR-55 runoff calculations?",
        answer=(
            "NRCS TR-55 Curve Numbers (CN) reflect land-use and hydrologic soil group. "
            "Typical values: Open water = 100; Impervious urban = 98; Heavily developed "
            "(HSG C/D) = 90–95; Suburban (HSG B) = 75–85; Woods in good condition "
            "(HSG A) = 30–36. Use county soil surveys (Web Soil Survey) to determine "
            "HSG, and combine with land-use data to compute composite CN. Higher CN "
            "values produce more runoff for the same rainfall depth."
        ),
        tags=["curve number", "cn", "tr-55", "nrcs", "runoff", "rainfall",
              "soil", "hsg", "urban", "impervious"],
        source="NRCS TR-55 (1986) / Web Soil Survey",
    ),
    KnowledgeEntry(
        question="How are NOAA PFDS rainfall frequencies used in flood analysis?",
        answer=(
            "NOAA Atlas 14 (Precipitation Frequency Data Server, PFDS) provides "
            "statistically derived rainfall depths for durations from 5 minutes to 60 days "
            "and return periods from 1 to 1000 years. These depths are used with "
            "hydrologic methods (e.g. TR-55, HEC-HMS) to estimate peak runoff and "
            "flood elevations. The CVG Rainfall Wizard queries PFDS via the hdsc.nws.noaa.gov "
            "REST API, returning mean precipitation depth (mm) for a given lat/lon, duration, "
            "and return period."
        ),
        tags=["pfds", "atlas 14", "noaa", "rainfall", "precipitation",
              "frequency", "return period", "duration", "hdsc"],
        source="NOAA Atlas 14 / PFDS hdsc.nws.noaa.gov",
    ),
    KnowledgeEntry(
        question="What is IDF and how is it different from PFDS?",
        answer=(
            "IDF stands for Intensity-Duration-Frequency. An IDF curve shows rainfall "
            "intensity (mm/hr or in/hr) as a function of storm duration for a given "
            "return period. PFDS (NOAA Atlas 14) provides the underlying frequency-depth "
            "data; IDF curves are derived by dividing depth by duration. IDF is used "
            "directly in rational method calculations (Q = CiA) and in design of "
            "stormwater infrastructure."
        ),
        tags=["idf", "intensity duration frequency", "pfds", "atlas 14",
              "rational method", "stormwater", "design storm"],
        source="NOAA Atlas 14 / ASCE 7",
    ),
    KnowledgeEntry(
        question="What GeoTIFF compression should I use for flood depth rasters?",
        answer=(
            "For cloud-optimised GeoTIFFs (COG), DEFLATE compression with PREDICTOR=2 "
            "is recommended for floating-point depth grids — it typically achieves "
            "50–70% size reduction with no data loss. LZW is also lossless but slightly "
            "less efficient. ZSTD (available in GDAL 3.1+) offers better compression "
            "ratios. Avoid JPEG compression for depth data (lossy). Tiling at 256×256 "
            "pixels enables efficient partial reads by GIS clients."
        ),
        tags=["geotiff", "cog", "compression", "deflate", "lzw", "zstd",
              "raster", "gdal", "tile"],
        source="OGC COG Specification / GDAL Documentation",
    ),
]


# ---------------------------------------------------------------------------
# Simple TF-IDF-style scorer
# ---------------------------------------------------------------------------

def _tokenise(text: str) -> List[str]:
    """Lower-case, strip punctuation, split on whitespace."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return [t for t in text.split() if len(t) > 1]


def _score_entry(query_tokens: List[str], entry: KnowledgeEntry) -> float:
    """Return a relevance score for *entry* given *query_tokens*."""
    # Build a token bag from question + answer + tags
    bag = (
        _tokenise(entry.question)
        + _tokenise(entry.answer)
        + [t.lower() for t in entry.tags]
    )
    bag_set = set(bag)
    bag_freq: Dict[str, int] = {}
    for t in bag:
        bag_freq[t] = bag_freq.get(t, 0) + 1

    score = 0.0
    for qt in query_tokens:
        if qt in bag_set:
            # TF component: term frequency normalised by bag length
            tf = bag_freq[qt] / max(len(bag), 1)
            # Tag bonus: exact tag match is weighted more heavily
            tag_bonus = 3.0 if qt in [t.lower() for t in entry.tags] else 1.0
            score += tf * tag_bonus

    return score


# ---------------------------------------------------------------------------
# Public search function
# ---------------------------------------------------------------------------

def search_knowledge(
    query: str,
    top_k: int = 3,
    min_score: float = 0.0,
    knowledge_base: Optional[List[KnowledgeEntry]] = None,
) -> List[KnowledgeEntry]:
    """Return the top-k most relevant knowledge entries for *query*.

    Parameters
    ----------
    query : str
        Free-text query string.
    top_k : int
        Maximum number of results to return.
    min_score : float
        Minimum relevance score threshold (0 returns all).
    knowledge_base : list[KnowledgeEntry] | None
        Custom knowledge base; defaults to the built-in KNOWLEDGE_BASE.

    Returns
    -------
    list[KnowledgeEntry]
        Ranked list of matching entries (most relevant first), each with
        the ``score`` field populated.
    """
    kb = knowledge_base if knowledge_base is not None else KNOWLEDGE_BASE
    query_tokens = _tokenise(query)

    if not query_tokens:
        return kb[:top_k]

    scored: List[Tuple[float, KnowledgeEntry]] = []
    for entry in kb:
        s = _score_entry(query_tokens, entry)
        if s > min_score:
            import copy
            e = copy.copy(entry)
            e.score = round(s, 4)
            scored.append((s, e))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [e for _, e in scored[:top_k]]
    log.debug("search_knowledge: query=%r  matches=%d", query, len(results))
    return results


def format_insights(
    entries: List[KnowledgeEntry],
    show_source: bool = True,
) -> str:
    """Format a list of knowledge entries as a human-readable string.

    Parameters
    ----------
    entries : list[KnowledgeEntry]
        Entries to format (typically from search_knowledge).
    show_source : bool
        Include the source citation.

    Returns
    -------
    str
        Formatted multi-line string.
    """
    if not entries:
        return "No relevant guidance found for this query."
    lines = []
    for i, e in enumerate(entries, 1):
        lines.append(f"[{i}] {e.question}")
        lines.append(f"    {e.answer}")
        if show_source and e.source:
            lines.append(f"    Source: {e.source}")
        if e.score:
            lines.append(f"    Relevance score: {e.score:.4f}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# InsightsEngine class
# ---------------------------------------------------------------------------

class InsightsEngine:
    """Persistent insights engine with query history.

    Parameters
    ----------
    knowledge_base : list[KnowledgeEntry] | None
        Custom knowledge base; defaults to built-in KNOWLEDGE_BASE.
    top_k : int
        Default number of results per query.
    """

    def __init__(
        self,
        knowledge_base: Optional[List[KnowledgeEntry]] = None,
        top_k: int = 3,
    ) -> None:
        self.kb = knowledge_base if knowledge_base is not None else KNOWLEDGE_BASE
        self.top_k = top_k
        self._history: List[Dict[str, Any]] = []

    def search(self, query: str, top_k: Optional[int] = None) -> List[KnowledgeEntry]:
        """Search the knowledge base and record the query in history."""
        k = top_k if top_k is not None else self.top_k
        results = search_knowledge(query, top_k=k, knowledge_base=self.kb)
        self._history.append({"query": query, "results": len(results)})
        return results

    def format(self, query: str, top_k: Optional[int] = None) -> str:
        """Search and return formatted output."""
        return format_insights(self.search(query, top_k))

    @property
    def history(self) -> List[Dict[str, Any]]:
        """Return a copy of the query history."""
        return list(self._history)

    def add_entry(self, entry: KnowledgeEntry) -> None:
        """Add a custom entry to this engine's knowledge base."""
        self.kb = list(self.kb) + [entry]
