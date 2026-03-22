# CVG GeoServ Processor — Roadmap

## v1.0.0 (Current)
- [x] Core ops: clip, reproject, mosaic, reclassify, zonal_stats, contour, convert, compound
- [x] Click CLI with run/web/validate/list-ops subcommands
- [x] FastAPI web UI with JSON job submission  
- [x] Recovery/checkpoint system for multi-job runs
- [x] PerformanceMonitor (tracemalloc + wall-clock)
- [x] Dataclass config + JSON loader
- [x] Docker + docker-compose + Caddy production stack
- [x] Sample config targeting Monroe County 1m SSW outputs

## v1.1.0 (Planned)
- [ ] Async job queue (background task submission via FastAPI BackgroundTasks)
- [ ] Job status polling endpoint (GET /status/{job_id})
- [ ] Webhook notification on job completion
- [ ] COG (Cloud Optimized GeoTIFF) validation step post-convert
- [ ] gdalwarp fallback for reproject if rasterio unavailable

## v1.2.0 (Planned)
- [ ] Batch mode: auto-discover all SSW TIFs in a directory, run pipeline
- [ ] SSW integration: call SSW CLI directly from GeoServ compound job
- [ ] SLR integration: call SLR CLI for projection offset before compound
- [ ] Rainfall integration: call Rainfall CLI for CN-runoff depth before compound
- [ ] UI improvements: job status table, progress bar via SSE

## v2.0.0 (Future)
- [ ] ArcPy backend option for ESRI environments
- [ ] PostgreSQL/PostGIS output support
- [ ] Map tile generation (XYZ tiles) from depth grids
- [ ] QGIS plugin wrapper
- [ ] Automated FEMA BFE comparison report
