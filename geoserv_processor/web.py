# -*- coding: utf-8 -*-
# ==============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# ==============================================================================
"""GeoServ Processor — FastAPI web UI.

Exposes:
  GET  /          → Web UI (HTML form to submit a config JSON)
  POST /run        → Submit a GeoServConfig JSON, execute jobs, return results
  GET  /health     → Health check (returns {"status": "ok", "version": "..."})
  GET  /ops        → List supported operations
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from geoserv_processor import __version__
from geoserv_processor.config import GeoServConfig, VALID_OPS

log = logging.getLogger(__name__)

app = FastAPI(
    title="CVG GeoServ Processor",
    description="Centralized geoprocessing engine for CVG wizard workflows.",
    version=__version__,
    docs_url="/api/docs-ui",
    redoc_url=None,
)

# ---------------------------------------------------------------------------
# Mount extended API routers
# ---------------------------------------------------------------------------
from geoserv_processor.api_jobs  import router as jobs_router   # noqa: E402
from geoserv_processor.api_noaa  import router as noaa_router   # noqa: E402
from geoserv_processor.api_ops   import router as ops_router    # noqa: E402

app.include_router(jobs_router)   # /api/jobs/*
app.include_router(noaa_router)   # /api/noaa/*
app.include_router(ops_router)    # /api/ops/*


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "version": __version__, "service": "geoserv-processor"}


# ---------------------------------------------------------------------------
# Ops list
# ---------------------------------------------------------------------------

@app.get("/ops")
async def ops_list() -> Dict[str, Any]:
    return {
        "version": __version__,
        "operations": sorted(VALID_OPS),
        "count": len(VALID_OPS),
    }


# ---------------------------------------------------------------------------
# Run endpoint
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    config: Dict[str, Any]


@app.post("/run")
async def run_job(req: RunRequest) -> JSONResponse:
    """Submit a GeoServConfig JSON body and execute all enabled jobs."""
    t0 = time.monotonic()
    try:
        cfg = GeoServConfig.from_dict(req.config)
        errors = cfg.validate()
        if errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "Config validation failed", "errors": errors},
            )
    except HTTPException:
        raise
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"Config validation error: {exc}")

    try:
        from geoserv_processor.processing import run_geoserv_job
        results = run_geoserv_job(cfg)
    except Exception as exc:
        log.exception("Unhandled error in run_geoserv_job")
        raise HTTPException(status_code=500, detail=str(exc))

    elapsed = round(time.monotonic() - t0, 2)
    n_ok = sum(1 for r in results if r["status"] == "success")
    return JSONResponse(content={
        "project_name": cfg.project_name,
        "jobs_total": len(results),
        "jobs_succeeded": n_ok,
        "jobs_failed": len(results) - n_ok,
        "elapsed_s": elapsed,
        "results": results,
    })


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------

_HTML_UI = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CVG GeoServ Processor</title>
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; background: #0f1923; color: #e8eaf0; margin: 0; padding: 0; }
  header { background: #1c2b3a; padding: 18px 32px; border-bottom: 2px solid #2e7d9e; display: flex; align-items: center; gap: 14px; }
  header h1 { font-size: 1.5rem; margin: 0; color: #7dd3fc; letter-spacing: 0.04em; }
  header .badge { background: #2e7d9e; color: #fff; border-radius: 4px; padding: 2px 10px; font-size: 0.8rem; }
  .container { max-width: 960px; margin: 36px auto; padding: 0 24px; }
  .card { background: #1c2b3a; border-radius: 8px; padding: 24px; margin-bottom: 24px; border: 1px solid #2a3f52; }
  .card h2 { margin-top: 0; color: #7dd3fc; font-size: 1.1rem; }
  textarea { width: 100%; min-height: 320px; font-family: 'Consolas', monospace; font-size: 0.88rem;
             background: #0f1923; color: #a8d8ea; border: 1px solid #2e7d9e; border-radius: 6px;
             padding: 12px; box-sizing: border-box; resize: vertical; }
  button { background: #2e7d9e; color: #fff; border: none; border-radius: 6px; padding: 10px 28px;
           font-size: 1rem; cursor: pointer; margin-top: 12px; }
  button:hover { background: #3a9dc0; }
  #result { font-family: 'Consolas', monospace; font-size: 0.85rem; white-space: pre-wrap;
            background: #0f1923; border: 1px solid #2a3f52; border-radius: 6px; padding: 14px;
            min-height: 80px; color: #a8d8ea; }
  .ops-list { display: flex; flex-wrap: wrap; gap: 8px; }
  .op-chip { background: #2a3f52; border-radius: 4px; padding: 4px 12px; font-size: 0.85rem; color: #7dd3fc; }
  .footer { text-align: center; color: #4a6070; font-size: 0.8rem; padding: 24px 0; }
</style>
</head>
<body>
<header>
  <h1>CVG GeoServ Processor</h1>
  <span class="badge">v{version}</span>
</header>
<div class="container">
  <div class="card">
    <h2>Supported Operations</h2>
    <div class="ops-list">
      {ops_chips}
    </div>
  </div>
  <div class="card">
    <h2>Submit GeoServConfig JSON</h2>
    <textarea id="config-input" spellcheck="false">{sample_config}</textarea>
    <button onclick="submitJob()">▶ Run Jobs</button>
  </div>
  <div class="card">
    <h2>Results</h2>
    <div id="result">Results will appear here after submitting a job...</div>
  </div>
</div>
<div class="footer">© Clearview Geographic, LLC — CVG GeoServ Processor v{version}</div>
<script>
async function submitJob() {{
  const cfg = document.getElementById('config-input').value;
  const resultEl = document.getElementById('result');
  resultEl.textContent = 'Running...';
  try {{
    const resp = await fetch('/run', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{config: JSON.parse(cfg)}})
    }});
    const data = await resp.json();
    resultEl.textContent = JSON.stringify(data, null, 2);
  }} catch (e) {{
    resultEl.textContent = 'Error: ' + e.message;
  }}
}}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Extension API — async job queue, job polling, metrics, config validate
# ---------------------------------------------------------------------------
from geoserv_processor.ext_api import router as _ext_router  # noqa: E402

app.include_router(_ext_router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    ops_chips = "\n      ".join(
        f'<span class="op-chip">{op}</span>' for op in sorted(VALID_OPS)
    )
    sample = json.dumps({
        "project_name": "example_reproject",
        "resume": False,
        "validate_inputs_exist": False,
        "max_retries": 0,
        "retry_delay_s": 2.0,
        "stop_on_error": False,
        "job_timeout_s": None,
        "jobs": [{
            "op": "reproject",
            "label": "reproject_to_wgs84",
            "enabled": True,
            "inputs": [{"path": "/data/depth_10yr.tif"}],
            "output": {"path": "/out/depth_10yr_4326.tif", "compress": "lzw", "tiled": True},
            "reproject": {"crs": "EPSG:4326", "resampling": "bilinear"}
        }]
    }, indent=2)
    html = _HTML_UI.format(version=__version__, ops_chips=ops_chips, sample_config=sample)
    return HTMLResponse(content=html)
