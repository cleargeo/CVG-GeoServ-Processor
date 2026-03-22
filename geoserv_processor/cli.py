# -*- coding: utf-8 -*-
# ==============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# ==============================================================================
"""GeoServ Processor -- Command-line interface.

Commands
--------
  run         Execute all jobs defined in a config JSON file.
  web         Launch the FastAPI web UI.
  validate    Validate a config JSON without running.
  list-ops    Print all supported geoprocessing operations.

Examples
--------
  python -m geoserv_processor.cli run --config my_config.json
  python -m geoserv_processor.cli web --host 0.0.0.0 --port 8003
  python -m geoserv_processor.cli validate --config my_config.json
  python -m geoserv_processor.cli list-ops
"""
from __future__ import annotations

import logging
import sys

import click

from geoserv_processor import __version__
from geoserv_processor.config import GeoServConfig, VALID_OPS


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)-30s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(__version__, prog_name="geoserv-processor")
def cli() -> None:
    """CVG GeoServ Processor -- centralized geoprocessing engine."""


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--config", "-c", required=True, type=click.Path(exists=True),
              help="Path to GeoServConfig JSON.")
@click.option("--resume/--no-resume", default=False,
              help="Resume from checkpoint if available.")
# -- Reliability overrides (CLI flags take precedence over JSON values) ------
@click.option("--validate-inputs/--no-validate-inputs", default=None,
              help="Pre-flight: verify all input files exist before starting.")
@click.option("--stop-on-error/--no-stop-on-error", default=None,
              help="Abort the pipeline immediately on the first job failure.")
@click.option("--max-retries", default=None, type=int, metavar="N",
              help="Retry each failed job up to N times (0 = no retry).")
@click.option("--retry-delay", default=None, type=float, metavar="SECONDS",
              help="Initial delay between retries in seconds (doubles on each attempt).")
@click.option("--job-timeout", default=None, type=float, metavar="SECONDS",
              help="Per-job wall-clock timeout in seconds (None = disabled).")
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Enable debug logging.")
def run(
    config: str,
    resume: bool,
    validate_inputs: "bool | None",
    stop_on_error: "bool | None",
    max_retries: "int | None",
    retry_delay: "float | None",
    job_timeout: "float | None",
    verbose: bool,
) -> None:
    """Execute all enabled jobs in CONFIG.

    Reliability flags (--validate-inputs, --stop-on-error, --max-retries,
    --retry-delay, --job-timeout) override the corresponding values in the
    JSON config when provided on the command line.
    """
    _setup_logging(verbose)

    try:
        cfg = GeoServConfig.from_json(config)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        click.echo(f"ERROR loading config: {exc}", err=True)
        sys.exit(1)

    # Apply CLI overrides for top-level flags
    if resume:
        cfg.resume = True
    if validate_inputs is not None:
        cfg.validate_inputs_exist = validate_inputs
    if stop_on_error is not None:
        cfg.stop_on_error = stop_on_error
    if max_retries is not None:
        cfg.max_retries = max_retries
    if retry_delay is not None:
        cfg.retry_delay_s = retry_delay
    if job_timeout is not None:
        cfg.job_timeout_s = job_timeout

    # Echo the effective reliability settings so users can confirm
    if verbose:
        click.echo(
            f"[reliability] validate_inputs_exist={cfg.validate_inputs_exist}  "
            f"max_retries={cfg.max_retries}  retry_delay_s={cfg.retry_delay_s}  "
            f"stop_on_error={cfg.stop_on_error}  job_timeout_s={cfg.job_timeout_s}"
        )

    from geoserv_processor.processing import run_geoserv_job
    results = run_geoserv_job(cfg)

    n_ok = sum(1 for r in results if r["status"] == "success")
    n_err = sum(1 for r in results if r["status"] == "error")
    click.echo(
        f"\nGeoServ complete: {n_ok}/{len(results)} jobs succeeded, {n_err} failed."
    )

    if n_err > 0:
        for r in results:
            if r["status"] == "error":
                click.echo(
                    f"  FAIL  Job {r['job_idx']} ({r['op']}): "
                    f"{r.get('error', 'unknown error')}",
                    err=True,
                )
        sys.exit(1)


# ---------------------------------------------------------------------------
# web
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--host", default="0.0.0.0", show_default=True, help="Bind host.")
@click.option("--port", default=8003, show_default=True, type=int, help="Bind port.")
@click.option("--reload", is_flag=True, default=False,
              help="Enable auto-reload (dev mode).")
@click.option("--verbose", "-v", is_flag=True, default=False)
def web(host: str, port: int, reload: bool, verbose: bool) -> None:
    """Launch the GeoServ Processor web UI."""
    _setup_logging(verbose)
    try:
        import uvicorn
    except ImportError:
        click.echo("ERROR: uvicorn not installed.  pip install uvicorn[standard]", err=True)
        sys.exit(1)

    click.echo(f"Starting GeoServ Processor Job API on http://{host}:{port}")
    click.echo(f"  API docs: http://{host}:{port}/api/docs")
    uvicorn.run(
        "geoserv_processor.api_jobs:app",
        host=host,
        port=port,
        reload=reload,
        log_level="debug" if verbose else "info",
    )


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--config", "-c", required=True, type=click.Path(exists=True),
              help="Path to config JSON.")
@click.option("--verbose", "-v", is_flag=True, default=False)
def validate(config: str, verbose: bool) -> None:
    """Validate a GeoServConfig JSON file without running any jobs."""
    _setup_logging(verbose)
    try:
        cfg = GeoServConfig.from_json(config)
        errors = cfg.validate()
        if errors:
            click.echo(f"Config has {len(errors)} validation error(s):", err=True)
            for e in errors:
                click.echo(f"  - {e}", err=True)
            sys.exit(1)

        n = len([j for j in cfg.jobs if j.enabled])
        click.echo(
            f"[OK] Config valid -- project={cfg.project_name!r}  {n} enabled job(s)"
        )
        for i, job in enumerate(cfg.jobs):
            status = "[ON]" if job.enabled else "[--]"
            click.echo(f"  {status} [{i}] op={job.op}  label={job.label or '(none)'}")
    except (FileNotFoundError, ValueError, KeyError) as exc:
        click.echo(f"[FAIL] Config invalid: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# list-ops
# ---------------------------------------------------------------------------

@cli.command("list-ops")
def list_ops() -> None:
    """Print all supported geoprocessing operations and their descriptions."""
    _OP_DOCS = {
        "clip":        "Clip a raster to an AOI polygon (GeoJSON or Shapefile).",
        "reproject":   "Reproject a raster to a target EPSG/WKT CRS.",
        "mosaic":      "Merge multiple rasters into a single mosaic.",
        "reclassify":  "Reclassify raster values by range-to-value rules.",
        "zonal_stats": "Compute zonal statistics (min/max/mean/sum/count) over polygon zones.",
        "contour":     "Generate contour lines or polygons from a depth/elevation grid.",
        "convert":     "Convert raster format, compression, or tiling (supports COG).",
        "compound":    "Combine SSW + SLR + Rainfall depth grids into a compound hazard raster.",
    }
    click.echo(f"\nCVG GeoServ Processor v{__version__} -- Supported Operations\n")
    click.echo(f"  {'Operation':<14} Description")
    click.echo("  " + "-" * 60)
    for op in sorted(VALID_OPS):
        click.echo(f"  {op:<14} {_OP_DOCS.get(op, '')}")
    click.echo()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    cli()


if __name__ == "__main__":
    main()
