# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor -- Main job execution engine.

Dispatches each JobConfig to the appropriate ops module, manages recovery
checkpointing, and reports progress via logging.

Reliability features
--------------------
- **Pre-flight input check** (``cfg.validate_inputs_exist=True``):
  All input raster paths are verified to exist before any job starts.
  Missing files are reported as errors immediately, before any disk I/O.

- **Per-job retry with exponential backoff** (``cfg.max_retries > 0``):
  Transient failures (file locks, I/O glitches) are automatically retried
  up to ``max_retries`` times with an initial delay of ``retry_delay_s``
  seconds that doubles on each attempt.

- **Stop-on-error** (``cfg.stop_on_error=True``):
  Abort the pipeline immediately after the first job failure instead of
  continuing to the next job.

- **Per-job wall-clock timeout** (``cfg.job_timeout_s > 0``):
  Each job is executed in a thread; if it exceeds the timeout it is
  cancelled and marked as an error.

Usage::

    from geoserv_processor.processing import run_geoserv_job
    from geoserv_processor.config import GeoServConfig

    cfg = GeoServConfig.from_json("my_config.json")
    results = run_geoserv_job(cfg)
    # results: list of result dicts with keys:
    #   job_idx, op, label, output_path, elapsed_s, status[, error]
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FuturesTimeout
from pathlib import Path
from typing import Any, Dict, List, Optional

from geoserv_processor.config import GeoServConfig, JobConfig
from geoserv_processor.monitoring import PerformanceMonitor
from geoserv_processor.recovery import RecoveryManager

log = logging.getLogger(__name__)

# Dispatcher map -- op name -> callable
_OP_REGISTRY: Dict[str, Any] = {}


def _register_ops() -> None:
    """Lazy-import and register all op runners."""
    if _OP_REGISTRY:
        return
    from geoserv_processor.ops.clip import run_clip
    from geoserv_processor.ops.reproject import run_reproject
    from geoserv_processor.ops.mosaic import run_mosaic
    from geoserv_processor.ops.reclassify import run_reclassify
    from geoserv_processor.ops.zonal_stats import run_zonal_stats
    from geoserv_processor.ops.contour import run_contour
    from geoserv_processor.ops.convert import run_convert
    from geoserv_processor.ops.compound import run_compound

    _OP_REGISTRY.update({
        "clip": run_clip,
        "reproject": run_reproject,
        "mosaic": run_mosaic,
        "reclassify": run_reclassify,
        "zonal_stats": run_zonal_stats,
        "contour": run_contour,
        "convert": run_convert,
        "compound": run_compound,
    })


# ---------------------------------------------------------------------------
# Pre-flight input validation
# ---------------------------------------------------------------------------

def _preflight_input_check(active_jobs: List[JobConfig]) -> List[str]:
    """Return a list of missing-file error strings (empty = all OK).

    Checks every ``inp.path`` for every enabled job.  Called only when
    ``cfg.validate_inputs_exist`` is True.
    """
    missing: List[str] = []
    for idx, job in enumerate(active_jobs):
        label = job.label or f"job_{idx}"
        for inp in job.inputs:
            if inp.path and not Path(inp.path).exists():
                missing.append(
                    f"[job {idx} '{label}' op={job.op}] "
                    f"input not found: {inp.path}"
                )
    return missing


# ---------------------------------------------------------------------------
# Single job runner (with dispatcher + optional timeout)
# ---------------------------------------------------------------------------

def _run_single_job(job: JobConfig, job_idx: int, total: int) -> str:
    """Execute one job and return its output path."""
    label = job.label or f"job_{job_idx}"
    log.info(
        "-" * 60 + "\n[GeoServ] JOB %d/%d  op=%-12s  label=%s",
        job_idx + 1, total, job.op, label,
    )
    runner = _OP_REGISTRY.get(job.op)
    if runner is None:
        raise ValueError(f"No runner registered for op '{job.op}'")
    return runner(job)


def _run_with_timeout(
    job: JobConfig,
    job_idx: int,
    total: int,
    timeout_s: Optional[float],
) -> str:
    """Run a single job, optionally enforcing a wall-clock timeout."""
    if timeout_s is None:
        return _run_single_job(job, job_idx, total)

    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_run_single_job, job, job_idx, total)
        try:
            return fut.result(timeout=timeout_s)
        except _FuturesTimeout:
            raise TimeoutError(
                f"Job {job_idx} (op={job.op}) exceeded timeout of {timeout_s}s"
            )


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------

def _run_with_retry(
    job: JobConfig,
    job_idx: int,
    total: int,
    max_retries: int,
    retry_delay_s: float,
    timeout_s: Optional[float],
) -> str:
    """Execute a job, retrying on failure with exponential backoff."""
    last_exc: Optional[Exception] = None
    delay = retry_delay_s

    for attempt in range(max_retries + 1):  # attempt 0 is the first try
        if attempt > 0:
            log.warning(
                "[GeoServ] Retry %d/%d for job %d (op=%s) after %.1fs delay...",
                attempt, max_retries, job_idx, job.op, delay,
            )
            time.sleep(delay)
            delay *= 2.0  # exponential backoff

        try:
            return _run_with_timeout(job, job_idx, total, timeout_s)
        except Exception as exc:
            last_exc = exc
            log.warning(
                "[GeoServ] Job %d attempt %d/%d failed: %s",
                job_idx, attempt + 1, max_retries + 1, exc,
            )

    # All attempts exhausted
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Main public entry point
# ---------------------------------------------------------------------------

def run_geoserv_job(cfg: GeoServConfig) -> List[Dict[str, Any]]:
    """Execute all enabled jobs in a GeoServConfig sequentially.

    Returns a list of result dicts with keys:
      - job_idx, op, label, output_path, elapsed_s, status[, error]

    Reliability controls applied from *cfg*:
      - ``validate_inputs_exist`` -- pre-flight file existence check
      - ``max_retries`` / ``retry_delay_s`` -- per-job retry with backoff
      - ``stop_on_error`` -- abort pipeline on first failure
      - ``job_timeout_s`` -- per-job wall-clock timeout
    """
    _register_ops()

    active_jobs = [j for j in cfg.jobs if j.enabled]
    n = len(active_jobs)
    log.info("=" * 60)
    log.info("[GeoServ] Project: %s  |  %d active job(s)", cfg.project_name, n)
    if cfg.max_retries:
        log.info("[GeoServ] Reliability: max_retries=%d  retry_delay=%.1fs",
                 cfg.max_retries, cfg.retry_delay_s)
    if cfg.job_timeout_s:
        log.info("[GeoServ] Reliability: job_timeout=%.1fs", cfg.job_timeout_s)
    if cfg.stop_on_error:
        log.info("[GeoServ] Reliability: stop_on_error=True")
    log.info("=" * 60)

    # -- Pre-flight input existence check ------------------------------------
    if cfg.validate_inputs_exist:
        log.info("[GeoServ] Pre-flight: checking %d input path(s)...",
                 sum(len(j.inputs) for j in active_jobs))
        missing = _preflight_input_check(active_jobs)
        if missing:
            log.error("[GeoServ] Pre-flight FAILED -- %d missing input(s):", len(missing))
            for m in missing:
                log.error("  %s", m)
            # Return error results for all jobs rather than aborting silently
            results_preflight = []
            for idx, job in enumerate(active_jobs):
                job_missing = [m for m in missing if f"[job {idx} " in m]
                err_detail = "; ".join(job_missing) if job_missing else "pre-flight: missing inputs in another job"
                results_preflight.append({
                    "job_idx": idx,
                    "op": job.op,
                    "label": job.label,
                    "output_path": None,
                    "elapsed_s": 0.0,
                    "status": "error",
                    "error": f"Pre-flight failed -- {err_detail}",
                })
            return results_preflight
        log.info("[GeoServ] Pre-flight OK -- all inputs present.")

    # -- Checkpoint recovery -------------------------------------------------
    recovery = RecoveryManager(
        recovery_dir=cfg.recovery_dir,
        project_name=cfg.project_name,
    )
    if cfg.resume:
        recovery.load()

    # -- Job loop ------------------------------------------------------------
    results: List[Dict[str, Any]] = []
    overall_monitor = PerformanceMonitor(label="total run")
    overall_monitor.start()

    for idx, job in enumerate(active_jobs):
        # Skip already-done checkpoints
        if cfg.resume and recovery.is_done(idx):
            log.info("[GeoServ] Skipping job %d/%d (%s) -- checkpoint says done.",
                     idx + 1, n, job.op)
            results.append({
                "job_idx": idx, "op": job.op, "label": job.label,
                "output_path": None, "elapsed_s": 0.0, "status": "skipped",
            })
            continue

        mon = PerformanceMonitor(label=f"{job.op}[{idx}]")
        mon.start()
        t0 = time.monotonic()

        try:
            out_path = _run_with_retry(
                job, idx, n,
                max_retries=cfg.max_retries,
                retry_delay_s=cfg.retry_delay_s,
                timeout_s=cfg.job_timeout_s,
            )
            elapsed = time.monotonic() - t0
            mon.stop()
            mon.log_summary(f"{job.op}[{idx}]")
            recovery.mark_done(idx, output_path=out_path, elapsed_s=elapsed)
            results.append({
                "job_idx": idx, "op": job.op, "label": job.label,
                "output_path": out_path, "elapsed_s": round(elapsed, 2),
                "status": "success",
            })
            log.info("[GeoServ] Job %d/%d complete in %.1fs -> %s",
                     idx + 1, n, elapsed, out_path)

        except Exception as exc:
            elapsed = time.monotonic() - t0
            mon.stop()
            log.error("[GeoServ] Job %d/%d FAILED after %.1fs: %s",
                      idx + 1, n, elapsed, exc)
            results.append({
                "job_idx": idx, "op": job.op, "label": job.label,
                "output_path": None, "elapsed_s": round(elapsed, 2),
                "status": "error", "error": str(exc),
            })

            if cfg.stop_on_error:
                log.error(
                    "[GeoServ] stop_on_error=True -- aborting pipeline after "
                    "job %d failure.", idx
                )
                # Mark all remaining jobs as aborted
                for remaining_idx, remaining_job in enumerate(active_jobs[idx + 1:], start=idx + 1):
                    results.append({
                        "job_idx": remaining_idx,
                        "op": remaining_job.op,
                        "label": remaining_job.label,
                        "output_path": None,
                        "elapsed_s": 0.0,
                        "status": "aborted",
                        "error": f"Pipeline aborted due to failure in job {idx}",
                    })
                break  # stop processing

    overall_monitor.stop()
    overall_monitor.log_summary("total run")

    n_ok = sum(1 for r in results if r["status"] == "success")
    n_err = sum(1 for r in results if r["status"] == "error")
    n_skipped = sum(1 for r in results if r["status"] in ("skipped", "aborted"))
    log.info("=" * 60)
    log.info("[GeoServ] DONE: %d/%d succeeded, %d failed, %d skipped/aborted, %.1fs total",
             n_ok, n, n_err, n_skipped, overall_monitor.elapsed_s)
    log.info("=" * 60)
    return results
