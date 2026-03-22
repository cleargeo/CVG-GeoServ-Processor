# GeoServ Processor — API Reference

## REST Endpoints

### GET /health
Returns service health status.

**Response:**
```json
{"status": "ok", "version": "1.0.0", "service": "geoserv-processor"}
```

### GET /ops
Returns list of supported operations.

**Response:**
```json
{
  "version": "1.0.0",
  "operations": ["clip","compound","contour","convert","mosaic","reclassify","reproject","zonal_stats"],
  "count": 8
}
```

### POST /run
Submit a GeoServConfig JSON body for execution.

**Request body:** A complete `GeoServConfig` JSON object.

**Response:**
```json
{
  "project_name": "my_project",
  "jobs_total": 2,
  "jobs_succeeded": 2,
  "jobs_failed": 0,
  "elapsed_s": 14.3,
  "results": [
    {
      "job_idx": 0,
      "op": "reproject",
      "label": "reproject_100yr",
      "output_path": "/out/depth_100yr_6437.tif",
      "elapsed_s": 7.2,
      "status": "success"
    }
  ]
}
```

## Config Schema

### GeoServConfig (root)
| Field | Type | Default | Description |
|---|---|---|---|
| `project_name` | string | `"geoserv"` | Project identifier |
| `jobs` | array[JobConfig] | required | List of geoprocessing jobs |
| `resume` | bool | `false` | Resume from checkpoint |
| `recovery_dir` | string | null | Path for checkpoint file |
| `validate_inputs_exist` | bool | `false` | Pre-flight: verify all input paths exist |
| `max_retries` | int | `0` | Retry failed jobs N times with exponential backoff |
| `retry_delay_s` | float | `2.0` | Initial retry delay in seconds |
| `stop_on_error` | bool | `false` | Abort pipeline on first job failure |
| `job_timeout_s` | float | null | Per-job wall-clock timeout in seconds |

### JobConfig
| Field | Type | Required | Description |
|---|---|---|---|
| `op` | string | ✓ | Operation: clip/reproject/mosaic/reclassify/zonal_stats/contour/convert/compound |
| `inputs` | array[InputRasterConfig] | ✓ | Input file(s) |
| `output` | OutputConfig | ✓* | Output file settings (*not required for zonal_stats/contour) |
| `label` | string | — | Human-readable label |
| `enabled` | bool | `true` | Set false to skip this job |
| `clip` | ClipConfig | when op=clip | AOI clip settings |
| `reproject` | ReprojectConfig | when op=reproject | CRS/resampling settings |
| `mosaic` | MosaicConfig | when op=mosaic | Merge settings |
| `reclassify` | ReclassifyConfig | when op=reclassify | Range rules |
| `zonal_stats` | ZonalStatsConfig | when op=zonal_stats | Zone polygon + stats |
| `contour` | ContourConfig | when op=contour | Interval/format settings |
| `convert` | ConvertConfig | when op=convert | Format/compress settings |
| `compound` | CompoundConfig | when op=compound | Aggregation method |

### OutputConfig
| Field | Type | Default | Description |
|---|---|---|---|
| `path` | string | required | Output file path |
| `compress` | string | `"lzw"` | GDAL compression |
| `tiled` | bool | `true` | Tiled GeoTIFF |
| `tile_size` | int | `256` | Tile width/height |
| `bigtiff` | string | `"IF_SAFER"` | BigTIFF mode |
| `nodata` | float | `-9999.0` | NoData value |
| `overwrite` | bool | `true` | Overwrite existing |
