# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor -- configuration dataclasses.

Two configuration families live here:

1. **Base wizard configs** (``BaseWizardConfig`` and helpers) -- inherited by
   the Rainfall, SLR, and Storm-Surge Wizards for their domain-specific
   top-level configuration.

2. **GeoServ job configs** (``GeoServConfig``, ``JobConfig``, and per-op
   config blocks) -- used by the centralized geoprocessing engine to describe
   a pipeline of raster operations (clip, reproject, mosaic, etc.).
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


def _dataclass_from_dict(klass: type, d: Dict[str, Any]) -> Any:
    """Construct a dataclass from a dict, silently ignoring unknown keys."""
    known = {f.name for f in dataclasses.fields(klass)}
    return klass(**{k: v for k, v in d.items() if k in known})


# ===========================================================================
# Section 1 -- Base wizard configuration helpers
# ===========================================================================

@dataclass
class RasterInput:
    """Wizard-level raster input descriptor (DEM, bathymetry, water-surface, etc.)."""

    path: str
    band: int = 1
    nodata: Optional[float] = None
    label: str = ""

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("RasterInput.path must not be empty.")
        if self.band < 1:
            raise ValueError("RasterInput.band must be >= 1.")


@dataclass
class VectorInput:
    """Wizard-level polygon/line/point vector input (AOI, mask, shoreline, etc.)."""

    path: str
    layer: Optional[str] = None
    label: str = ""

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("VectorInput.path must not be empty.")


@dataclass
class NoaaConfig:
    """Shared NOAA API configuration parameters."""

    station_id: str = ""
    datum: str = "NAVD"
    units: str = "metric"
    timeout_s: int = 30
    retries: int = 3


@dataclass
class ProcessingConfig:
    """Shared raster processing parameters (wizard-level)."""

    target_crs: str = "EPSG:4326"
    target_resolution_m: float = 10.0
    resampling_method: str = "bilinear"
    clip_to_aoi: bool = True
    fill_nodata: bool = True
    depth_threshold_m: float = 0.0
    max_workers: int = 4


@dataclass
class WizardOutputConfig:
    """Wizard-level output file / directory configuration."""

    output_dir: str = "./output"
    prefix: str = "cvg"
    write_geotiff: bool = True
    write_vector: bool = True
    write_pdf: bool = True
    write_json: bool = True
    overwrite: bool = True

    def resolved_dir(self) -> Path:
        p = Path(self.output_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p


@dataclass
class BaseWizardConfig:
    """Top-level base configuration inherited by all CVG Wizard configs."""

    wizard_name: str = "CVG GeoServ Processor"
    wizard_version: str = "1.0.0"
    site_name: str = ""
    noaa: NoaaConfig = field(default_factory=NoaaConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    outputs: WizardOutputConfig = field(default_factory=WizardOutputConfig)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, path: Optional[str] = None, indent: int = 2) -> str:
        data = json.dumps(self.to_dict(), indent=indent, default=str)
        if path:
            Path(path).write_text(data, encoding="utf-8")
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseWizardConfig":
        return cls(**data)

    @classmethod
    def from_json(cls, path: str) -> "BaseWizardConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def validate(self) -> List[str]:
        errors: List[str] = []
        if self.processing.target_resolution_m <= 0:
            errors.append("processing.target_resolution_m must be > 0")
        if self.processing.max_workers < 1:
            errors.append("processing.max_workers must be >= 1")
        return errors


# ===========================================================================
# Section 2 -- GeoServ job configuration (operation pipeline)
# ===========================================================================

VALID_OPS: frozenset = frozenset([
    "clip",
    "reproject",
    "mosaic",
    "reclassify",
    "zonal_stats",
    "contour",
    "convert",
    "compound",
])


# ---------------------------------------------------------------------------
# Shared per-job I/O descriptors
# ---------------------------------------------------------------------------

@dataclass
class InputRasterConfig:
    """Per-job input raster descriptor."""

    path: str = ""
    band: int = 1
    label: str = ""
    nodata: Optional[float] = None

    def __post_init__(self) -> None:
        if self.band < 1:
            raise ValueError("InputRasterConfig.band must be >= 1.")


@dataclass
class OutputConfig:
    """Per-job output raster descriptor."""

    path: str = ""
    nodata: float = -9999.0
    compress: str = "lzw"
    tiled: bool = True
    tile_size: int = 256
    bigtiff: str = "IF_SAFER"
    overwrite: bool = True


# ---------------------------------------------------------------------------
# Per-operation config blocks
# ---------------------------------------------------------------------------

@dataclass
class ClipConfig:
    """Config block for the 'clip' operation."""

    aoi_path: Optional[str] = None
    """Path to a vector AOI file (shapefile, GeoJSON, GPKG)."""

    aoi_geojson: Optional[Any] = None
    """Inline GeoJSON geometry dict (alternative to aoi_path)."""

    crop: bool = True
    """Crop the output extent to the AOI bounding box."""

    all_touched: bool = False
    """Include pixels that touch the AOI boundary (rasterio all_touched)."""


@dataclass
class ReprojectConfig:
    """Config block for the 'reproject' operation."""

    crs: str = "EPSG:4326"
    """Target CRS (EPSG string, WKT, or PROJ string)."""

    resampling: str = "bilinear"
    """Rasterio resampling method name."""

    target_resolution: Optional[float] = None
    """Output pixel resolution in the target CRS units.  None = auto."""


@dataclass
class MosaicConfig:
    """Config block for the 'mosaic' operation."""

    resampling: str = "first"
    """Rasterio merge strategy: 'first', 'last', 'min', 'max', 'sum'."""


@dataclass
class ReclassifyRule:
    """A single value-range reclassification rule."""

    vmin: float = 0.0
    """Lower bound (inclusive)."""

    vmax: float = 0.0
    """Upper bound (exclusive, or inclusive depending on implementation)."""

    new_value: float = 0.0
    """Replacement value for pixels in [vmin, vmax)."""


@dataclass
class ReclassifyConfig:
    """Config block for the 'reclassify' operation."""

    rules: List[ReclassifyRule] = field(default_factory=list)
    """Ordered list of reclassification rules."""

    default_value: float = -9999.0
    """Value assigned to pixels that match no rule."""


@dataclass
class ZonalStatsConfig:
    """Config block for the 'zonal_stats' operation."""

    zones_path: str = ""
    """Path to the polygon zones vector file."""

    zone_id_field: str = "zone_id"
    """Attribute field used as zone identifier."""

    stats: List[str] = field(default_factory=lambda: ["mean", "min", "max"])
    """Statistics to compute: 'mean', 'min', 'max', 'sum', 'count', 'std'."""

    output_path: str = "zonal_stats.json"
    """Output file path for the statistics table."""

    output_format: str = "json"
    """Output format: 'json', 'csv', or 'gpkg'."""


@dataclass
class ContourConfig:
    """Config block for the 'contour' operation."""

    interval: float = 1.0
    """Contour interval in raster units."""

    base: float = 0.0
    """Base contour value (origin of the interval series)."""

    unit: str = "m"
    """Label for the elevation unit (stored in output feature properties)."""

    min_value: Optional[float] = None
    """Minimum value to generate contours from (None = auto from data)."""

    max_value: Optional[float] = None
    """Maximum value to generate contours to (None = auto from data)."""

    geometry_type: str = "linestring"
    """Output geometry type: 'linestring' or 'polygon'."""

    elevation_field: str = "elevation"
    """Output feature attribute name for elevation value."""

    output_format: str = "geojson"
    """Output format: 'geojson', 'shapefile', or 'gpkg'."""


@dataclass
class ConvertConfig:
    """Config block for the 'convert' operation."""

    compress: str = "lzw"
    """Output compression codec."""

    tiled: bool = True
    """Write internally tiled GeoTIFF."""

    tile_size: int = 256
    """Tile width/height in pixels."""

    bigtiff: str = "IF_SAFER"
    """BigTIFF flag passed to rasterio."""

    cog: bool = False
    """Build COG internal overviews after writing."""


@dataclass
class CompoundConfig:
    """Config block for the 'compound' operation."""

    method: str = "max"
    """Aggregation method: 'max', 'sum', or 'mean'."""


# ---------------------------------------------------------------------------
# JobConfig -- one pipeline step
# ---------------------------------------------------------------------------

@dataclass
class JobConfig:
    """Describes a single geoprocessing job step within a GeoServ pipeline."""

    op: str = ""
    """Operation name -- must be one of VALID_OPS."""

    label: str = ""
    """Human-readable label used in logs and reports."""

    enabled: bool = True
    """Set to False to skip this job without removing it from the config."""

    inputs: List[InputRasterConfig] = field(default_factory=list)
    """Input raster file(s).  Most ops use only inputs[0]; mosaic/compound use all."""

    output: OutputConfig = field(default_factory=OutputConfig)
    """Output raster descriptor."""

    # -- Per-op config blocks (only one should be set per job) ---------------
    clip:       Optional[ClipConfig]       = None
    reproject:  Optional[ReprojectConfig]  = None
    mosaic:     Optional[MosaicConfig]     = None
    reclassify: Optional[ReclassifyConfig] = None
    zonal_stats: Optional[ZonalStatsConfig] = None
    contour:    Optional[ContourConfig]    = None
    convert:    Optional[ConvertConfig]    = None
    compound:   Optional[CompoundConfig]   = None

    def __post_init__(self) -> None:
        if self.op and self.op not in VALID_OPS:
            raise ValueError(
                f"JobConfig.op '{self.op}' is not valid.  "
                f"Must be one of: {sorted(VALID_OPS)}"
            )

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "JobConfig":
        """Deserialise a JobConfig from a plain dict (e.g. from JSON)."""
        d = dict(d)

        # Deserialise nested InputRasterConfig list (ignore unknown fields)
        raw_inputs = d.pop("inputs", [])
        inputs = [
            _dataclass_from_dict(InputRasterConfig, i) if isinstance(i, dict) else i
            for i in raw_inputs
        ]

        # Deserialise output (ignore unknown fields)
        raw_out = d.pop("output", {})
        output = _dataclass_from_dict(OutputConfig, raw_out) if isinstance(raw_out, dict) else raw_out

        # Deserialise per-op config blocks (unknown keys are silently ignored)
        def _pop(key: str, klass: type) -> Optional[Any]:
            val = d.pop(key, None)
            if val is None:
                return None
            if isinstance(val, dict):
                if key == "reclassify":
                    rules = [
                        _dataclass_from_dict(ReclassifyRule, r) if isinstance(r, dict) else r
                        for r in val.get("rules", [])
                    ]
                    val = dict(val)
                    val["rules"] = rules
                return _dataclass_from_dict(klass, val)
            return val

        clip        = _pop("clip",        ClipConfig)
        reproject   = _pop("reproject",   ReprojectConfig)
        mosaic      = _pop("mosaic",      MosaicConfig)
        reclassify  = _pop("reclassify",  ReclassifyConfig)
        zonal_stats = _pop("zonal_stats", ZonalStatsConfig)
        contour     = _pop("contour",     ContourConfig)
        convert     = _pop("convert",     ConvertConfig)
        compound    = _pop("compound",    CompoundConfig)

        # Filter remaining top-level keys to known JobConfig fields
        known_job = {f.name for f in dataclasses.fields(cls)}
        extra = {k: v for k, v in d.items() if k in known_job}
        return cls(
            inputs=inputs,
            output=output,
            clip=clip,
            reproject=reproject,
            mosaic=mosaic,
            reclassify=reclassify,
            zonal_stats=zonal_stats,
            contour=contour,
            convert=convert,
            compound=compound,
            **extra,
        )


# ---------------------------------------------------------------------------
# GeoServConfig -- top-level pipeline config
# ---------------------------------------------------------------------------

@dataclass
class GeoServConfig:
    """Top-level configuration for a CVG GeoServ Processor pipeline.

    Holds a list of JobConfig steps plus project-level settings.

    Example::

        cfg = GeoServConfig.from_json("sample_config.json")
        errors = cfg.validate()
        if not errors:
            results = run_geoserv_job(cfg)
    """

    project_name: str = "geoserv"
    """Short project identifier used in logs and checkpoint filenames."""

    jobs: List[JobConfig] = field(default_factory=list)
    """Ordered list of processing steps."""

    resume: bool = False
    """If True, skip already-completed jobs using the checkpoint file."""

    recovery_dir: Optional[str] = None
    """Directory for checkpoint files.  None disables recovery."""

    # ------------------------------------------------------------------
    # Reliability controls
    # ------------------------------------------------------------------
    validate_inputs_exist: bool = False
    """Pre-flight check: verify all input raster paths exist before starting."""

    max_retries: int = 0
    """Number of times to retry a failed job before marking it as an error."""

    retry_delay_s: float = 2.0
    """Initial delay (seconds) between retries.  Doubles on each attempt."""

    stop_on_error: bool = False
    """If True, abort the entire pipeline on the first job failure."""

    job_timeout_s: Optional[float] = None
    """Per-job wall-clock timeout in seconds.  None = no timeout."""

    # ------------------------------------------------------------------
    def validate(self) -> List[str]:
        """Return a list of validation error strings (empty = valid)."""
        errors: List[str] = []
        for i, job in enumerate(self.jobs):
            tag = f"jobs[{i}] op={job.op!r}"
            if not job.op:
                errors.append(f"{tag}: op must not be empty.")
            elif job.op not in VALID_OPS:
                errors.append(f"{tag}: unknown op '{job.op}'.  Valid: {sorted(VALID_OPS)}")
            if not job.inputs and job.op not in ("mosaic",):
                errors.append(f"{tag}: at least one input is required.")
            if job.inputs:
                for j, inp in enumerate(job.inputs):
                    if not inp.path:
                        errors.append(f"{tag} inputs[{j}]: path must not be empty.")
            if not job.output.path:
                errors.append(f"{tag}: output.path must not be empty.")
        return errors

    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, path: Optional[str] = None, indent: int = 2) -> str:
        """Serialise to JSON, optionally writing to file."""
        data = json.dumps(self.to_dict(), indent=indent, default=str)
        if path:
            Path(path).write_text(data, encoding="utf-8")
        return data

    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GeoServConfig":
        """Deserialise from a plain dict (unknown top-level keys are silently ignored)."""
        d = dict(d)
        raw_jobs = d.pop("jobs", [])
        jobs = [
            JobConfig.from_dict(j) if isinstance(j, dict) else j
            for j in raw_jobs
        ]
        known = {f.name for f in dataclasses.fields(cls)}
        extra = {k: v for k, v in d.items() if k in known}
        return cls(jobs=jobs, **extra)

    @classmethod
    def from_json(cls, path: str) -> "GeoServConfig":
        """Load configuration from a JSON file (handles UTF-8 BOM transparently)."""
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return cls.from_dict(data)
