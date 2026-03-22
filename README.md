# CVG GeoServ Processor

> **© Clearview Geographic, LLC — All Rights Reserved | Est. 2018**  
> Proprietary Software — Internal Use Only  
> Developed under the CVG Agentic Development Framework (ADF)

---

## Overview

**CVG GeoServ Processor** is the shared geospatial processing engine powering the
CVG Wizard Suite:

| Wizard | Package | Port |
|--------|---------|------|
| Rainfall Wizard | `rainfall-wizard` | 8002 |
| SLR Wizard | `slr-wizard` | 8001 |
| Storm Surge Wizard | `storm-surge-wizard` | 8003 |

It consolidates raster/vector I/O, DEM-based flood depth computation, NOAA API
access, performance monitoring, report generation, and knowledge-base search into
a single installable library so they don’t need to be duplicated across every wizard.

---

## Module Reference

| Module | Description |
|--------|-------------|
| `geoserv_processor.config` | Dataclasses: `GeoServConfig`, `JobConfig`, `BaseWizardConfig`, `OutputConfig`, op configs, … |
| `geoserv_processor.io` | Raster I/O (`read_raster`, `write_raster`, `load_aoi`, `RasterData`) |
| `geoserv_processor.processing` | Job engine (`run_geoserv_job`) — dispatches ops, retry, timeout, stop-on-error |
| `geoserv_processor.depth` | Hydrology: `compute_depth_grid`, `inundate_dem`, `compute_compound_depth`, `classify_depth`, … |
| `geoserv_processor.ops` | Per-operation runners: clip, reproject, mosaic, reclassify, zonal_stats, contour, convert, compound |
| `geoserv_processor.recovery` | Checkpoint/resume manager (`RecoveryManager`) |
| `geoserv_processor.noaa` | NOAA CO-OPS + PFDS clients, TR-083 SLR tables |
| `geoserv_processor.monitoring` | Timing (`StepTimer`, `PerformanceMonitor`) and resource tracking |
| `geoserv_processor.report` | PDF + JSON report generation (`ReportBuilder`, `ReportData`) |
| `geoserv_processor.insights` | Knowledge-base search (`search_knowledge`, `InsightsEngine`) |
| `geoserv_processor.web` | FastAPI app (`app`) with `/health`, `/ops`, `/run` endpoints and HTML UI |
| `geoserv_processor.cli` | Click CLI: `run`, `web`, `validate`, `list-ops` commands |
| `geoserv_processor.utils` | Unit conversion, coordinate math, string helpers |

---

## Installation

```bash
# Editable install (recommended for development)
pip install -e "G:\07_APPLICATIONS_TOOLS\CVG_GeoServ_Processor"

# Or add to wizard requirements.txt:
# -e ../CVG_GeoServ_Processor
```

### Dependencies

```
numpy>=1.26         rasterio>=1.3        fiona>=1.9
shapely>=2.0        geopandas>=0.14      scikit-image>=0.22
click>=8.1          fastapi>=0.110       uvicorn[standard]>=0.29
pydantic>=2.0       reportlab>=4.0       psutil>=5.9
```

---

## Quick Start

### Flood Depth Grid from DEM + WSE

```python
from geoserv_processor.io import read_raster, write_raster, RasterData
from geoserv_processor.depth import inundate_dem

data, profile = read_raster("path/to/dem.tif")
dem_data = RasterData(array=data, transform=profile["transform"], crs=profile.get("crs"))
depth_data = inundate_dem(dem_data, wse_elev_m=2.5)
write_raster("output/depth_grid.tif", depth_data.array, profile, nodata=-9999.0)
```

### NOAA SLR Projection

```python
from geoserv_processor.noaa import NoaaCoOpsClient

client = NoaaCoOpsClient("8724580")          # Key West, FL
print(client.get_slr("intermediate", 2075))  # → ~0.68 m
```

### NOAA PFDS Rainfall

```python
from geoserv_processor.noaa import fetch_pfds_precipitation

depth_mm = fetch_pfds_precipitation(
    lat=29.65, lon=-81.63,
    duration_hr=24, return_period_yr=100
)
print(f"100-yr / 24-hr rainfall: {depth_mm:.1f} mm")
```

### Compound Flood Analysis

```python
from geoserv_processor.depth import compute_compound_depth

compound = compute_compound_depth(
    [surge_depth, rainfall_depth, slr_depth],
    method="max",   # worst-case combination
)
```

### Hazard Knowledge Search

```python
from geoserv_processor.insights import search_knowledge, format_insights

results = search_knowledge("what is a 100 year flood", top_k=2)
print(format_insights(results))
```

### Report Generation

```python
from geoserv_processor.report import ReportBuilder

rb = ReportBuilder("./output", "site_100yr")
rb.data.title = "100-Year Flood Depth Analysis"
rb.data.inputs["Station"] = "8724580 (Key West, FL)"
rb.data.results["Max Depth (m)"] = "3.41"
rb.data.results["Flooded Area (km²)"] = "12.7"
json_path, pdf_path = rb.build()
```

### Web Server

```bash
# Start via CLI (recommended):
python -m geoserv_processor.cli web --host 0.0.0.0 --port 8003
```

```python
# Or programmatically:
import uvicorn
uvicorn.run("geoserv_processor.web:app", host="0.0.0.0", port=8003)
```

```
# Endpoints:
# GET  /health  → {"status": "ok", "version": "1.0.0", "service": "geoserv-processor"}
# GET  /ops     → {"operations": [...], "count": 8}
# POST /run     → submit GeoServConfig JSON, returns job results
```

---

## Integration with CVG Wizards

Each wizard imports from `geoserv_processor` and extends the base classes:

```python
# In storm_surge_wizard/config.py
from geoserv_processor.config import BaseWizardConfig
from dataclasses import dataclass

@dataclass
class StormSurgeConfig(BaseWizardConfig):
    wizard_name: str = "CVG Storm Surge Wizard"
    wizard_version: str = "1.4.1"
    surge_scenario: str = "100yr"
    # ... additional fields ...
```

```python
# In storm_surge_wizard/web.py — mount the shared GeoServ app or call its functions directly:
from geoserv_processor.processing import run_geoserv_job
from geoserv_processor.config import GeoServConfig

# Build a wizard-specific job config and run it through the shared engine:
cfg = GeoServConfig(project_name="storm_surge_run", jobs=[...])
results = run_geoserv_job(cfg)
```

---

## Testing

```bash
cd "G:\07_APPLICATIONS_TOOLS\CVG_GeoServ_Processor"
python -m pytest tests/ -v
```

---

## Directory Structure

```
CVG_GeoServ_Processor/
├── geoserv_processor/
│   ├── __init__.py       # Package init, __version__, public API exports
│   ├── __main__.py       # Entry point (python -m geoserv_processor)
│   ├── config.py         # GeoServConfig, JobConfig, BaseWizardConfig, op configs, …
│   ├── io.py             # Raster I/O (read_raster, write_raster, RasterData)
│   ├── processing.py     # Job engine (run_geoserv_job) — dispatch, retry, timeout
│   ├── depth.py          # Hydrology: compute_depth_grid, inundate_dem, classify_depth, …
│   ├── recovery.py       # Checkpoint/resume (RecoveryManager)
│   ├── noaa.py           # NOAA CO-OPS + PFDS + TR-083 SLR clients
│   ├── monitoring.py     # StepTimer, PerformanceMonitor, ResourceSnapshot
│   ├── report.py         # PDF + JSON report (ReportBuilder, ReportData)
│   ├── insights.py       # Knowledge-base search (InsightsEngine)
│   ├── web.py            # FastAPI app (app) — /health, /ops, /run + HTML UI
│   ├── cli.py            # Click CLI: run, web, validate, list-ops
│   ├── utils.py          # Unit conversion, coordinate math, string helpers
│   └── ops/
│       ├── __init__.py
│       ├── clip.py
│       ├── reproject.py
│       ├── mosaic.py
│       ├── reclassify.py
│       ├── zonal_stats.py
│       ├── contour.py
│       ├── convert.py
│       └── compound.py
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_io.py
│   ├── test_processing.py
│   ├── test_noaa.py
│   ├── test_monitoring.py
│   ├── test_report.py
│   ├── test_insights.py
│   └── test_utils.py
├── docs/
│   ├── API_REFERENCE.md
│   └── index.md
├── caddy/
│   └── Caddyfile
├── pyproject.toml
├── setup.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── pytest.ini
├── .flake8
├── .gitignore
├── .dockerignore
├── README.md
├── ROADMAP.md
├── CONTRIBUTING.md
├── LICENSE.md
├── SECURITY.md
├── start-dev.bat
├── start-prod-direct.bat
└── run_tests.bat
```

---

## Author

**Alex Zelenski, GISP**  
Clearview Geographic, LLC  
[azelenski@clearviewgeographic.com](mailto:azelenski@clearviewgeographic.com)  
[www.clearviewgeographic.com](https://www.clearviewgeographic.com)  
GitHub: [@azelenski_cvg](https://github.com/azelenski_cvg) | [@clearview-geographic](https://github.com/clearview-geographic)
