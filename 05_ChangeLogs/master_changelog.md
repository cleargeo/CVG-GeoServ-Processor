# CVG GeoServ Processor — Master Changelog

## v1.0.0 — 2026-03-21

### Initial Release

**New package: `geoserv-processor`** — Centralized geoprocessing engine for the CVG wizard suite.

#### Core Operations
- `clip` — Clip raster to AOI polygon (rasterio.mask)
- `reproject` — Reproject raster to target CRS (rasterio.warp)
- `mosaic` — Merge multiple rasters (rasterio.merge)
- `reclassify` — Value range reclassification (numpy)
- `zonal_stats` — Zonal statistics over polygon zones (geopandas + rasterio)
- `contour` — Contour line/polygon generation (scikit-image)
- `convert` — Format/compression conversion + COG overviews
- `compound` — Compound hazard grid combination (max/sum/mean)

#### Infrastructure
- Click CLI: `run`, `web`, `validate`, `list-ops`
- FastAPI web UI on port 8003 with JSON job submission
- Recovery/checkpoint system (JSON checkpoint file)
- PerformanceMonitor (tracemalloc + wall-clock)
- Dataclass config + JSON loader with validation
- Docker + docker-compose + Caddy production stack
- Sample config targeting Monroe County 1m SSW outputs (EPSG:6437 reproject + contours)

#### Integration
- Designed to consume outputs from SSW (storm_surge_wizard), SLR (slr_wizard), and Rainfall (rainfall_wizard)
- Follows identical CVG ADF code patterns, copyright headers, and module structure
