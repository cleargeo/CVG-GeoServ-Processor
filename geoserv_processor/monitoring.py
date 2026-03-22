# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor — shared performance monitoring and timing utilities.

Provides lightweight instrumentation used across the CVG Wizard Suite to track
execution timing, memory usage, and step-level performance metrics.

Public API
----------
PerformanceMonitor
    Context manager + decorator for timing code blocks.
StepTimer
    Named-step timing accumulator for multi-step pipelines.
ResourceSnapshot
    Lightweight memory/CPU snapshot (psutil optional).
log_performance(label, elapsed_s, extra) -> None
    Write a structured performance log entry.
format_elapsed(seconds) -> str
    Human-readable elapsed time string.
"""

from __future__ import annotations

import functools
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

log = logging.getLogger(__name__)

# Optional psutil for memory tracking
try:
    import psutil as _psutil
    _HAS_PSUTIL = True
except ImportError:
    _psutil = None  # type: ignore
    _HAS_PSUTIL = False


# ---------------------------------------------------------------------------
# Resource snapshot
# ---------------------------------------------------------------------------

@dataclass
class ResourceSnapshot:
    """A snapshot of system resource usage at a point in time."""

    timestamp: float = field(default_factory=time.monotonic)
    rss_mb: float = 0.0          # Resident set size (MB)
    vms_mb: float = 0.0          # Virtual memory size (MB)
    cpu_pct: float = 0.0         # Process CPU percent

    @classmethod
    def capture(cls) -> "ResourceSnapshot":
        """Capture current process resource usage."""
        snap = cls(timestamp=time.monotonic())
        if _HAS_PSUTIL:
            try:
                proc = _psutil.Process()
                mem = proc.memory_info()
                snap.rss_mb = mem.rss / 1_048_576
                snap.vms_mb = mem.vms / 1_048_576
                snap.cpu_pct = proc.cpu_percent(interval=None)
            except Exception:
                pass
        return snap

    def delta_mb(self, other: "ResourceSnapshot") -> float:
        """Return change in RSS (MB) relative to *other* snapshot."""
        return self.rss_mb - other.rss_mb


# ---------------------------------------------------------------------------
# Step-level timing
# ---------------------------------------------------------------------------

@dataclass
class StepRecord:
    """Record for a single named pipeline step."""
    name: str
    start: float
    end: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed(self) -> float:
        return (self.end or time.monotonic()) - self.start

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.name,
            "elapsed_s": round(self.elapsed, 4),
            **self.extra,
        }


class StepTimer:
    """Named-step timing accumulator for multi-step pipelines.

    Usage
    -----
    ::

        timer = StepTimer("my_pipeline")
        with timer.step("load_dem"):
            data = read_raster(path)
        with timer.step("inundate"):
            depth = inundate_dem(data, wse)
        print(timer.summary())
    """

    def __init__(self, pipeline_name: str = "") -> None:
        self.pipeline_name = pipeline_name
        self._steps: List[StepRecord] = []
        self._start = time.monotonic()

    @contextmanager
    def step(self, name: str, **extra: Any) -> Generator[None, None, None]:
        """Context manager to time a named step."""
        rec = StepRecord(name=name, start=time.monotonic(), extra=extra)
        self._steps.append(rec)
        try:
            yield
        finally:
            rec.end = time.monotonic()
            log.debug("[%s] step '%s' finished in %.3f s",
                      self.pipeline_name, name, rec.elapsed)

    @property
    def total_elapsed(self) -> float:
        """Wall-clock seconds since this StepTimer was created."""
        return time.monotonic() - self._start

    def steps(self) -> List[Dict[str, Any]]:
        """Return list of step records as dicts."""
        return [s.to_dict() for s in self._steps]

    def summary(self) -> str:
        """Return a human-readable summary table."""
        lines = [f"Pipeline: {self.pipeline_name}"]
        lines.append(f"{'Step':<30} {'Elapsed':>10}")
        lines.append("-" * 42)
        for rec in self._steps:
            lines.append(f"{rec.name:<30} {format_elapsed(rec.elapsed):>10}")
        lines.append("-" * 42)
        lines.append(f"{'TOTAL':<30} {format_elapsed(self.total_elapsed):>10}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline": self.pipeline_name,
            "total_elapsed_s": round(self.total_elapsed, 4),
            "steps": self.steps(),
        }


# ---------------------------------------------------------------------------
# PerformanceMonitor context manager / decorator
# ---------------------------------------------------------------------------

class PerformanceMonitor:
    """Context manager and decorator for timing code blocks.

    Can be used as a context manager::

        with PerformanceMonitor("load_raster") as mon:
            data = read_raster(path)
        print(mon.elapsed_s)

    Or as a decorator::

        @PerformanceMonitor.wrap("process_dem")
        def process(dem_path):
            ...
    """

    def __init__(self, label: str = "", log_level: int = logging.DEBUG) -> None:
        self.label = label
        self.log_level = log_level
        self._start: float = 0.0
        self._end: float = 0.0
        self._snapshot_start: Optional[ResourceSnapshot] = None
        self._snapshot_end: Optional[ResourceSnapshot] = None

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "PerformanceMonitor":
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()
        self.log_summary(self.label)

    # ------------------------------------------------------------------
    # Imperative protocol (used by processing.py job loop)
    # ------------------------------------------------------------------

    def start(self) -> "PerformanceMonitor":
        """Start (or restart) the timer.  Returns self for chaining."""
        self._start = time.perf_counter()
        self._end = 0.0
        self._snapshot_start = ResourceSnapshot.capture()
        self._snapshot_end = None
        return self

    def stop(self) -> float:
        """Stop the timer and capture end snapshot.  Returns elapsed seconds."""
        self._end = time.perf_counter()
        self._snapshot_end = ResourceSnapshot.capture()
        return self.elapsed_s

    def log_summary(self, label: str = "") -> None:
        """Emit a performance log entry to the logger."""
        tag = label or self.label
        log_performance(
            tag,
            self.elapsed_s,
            extra={"rss_delta_mb": round(self.memory_delta_mb, 2)},
            level=self.log_level,
        )

    @property
    def elapsed_s(self) -> float:
        """Elapsed time in seconds (running if not stopped, final otherwise)."""
        end = self._end if self._end else time.perf_counter()
        return end - self._start

    @property
    def memory_delta_mb(self) -> float:
        """Change in process RSS (MB) during this block."""
        if self._snapshot_start and self._snapshot_end:
            return self._snapshot_end.delta_mb(self._snapshot_start)
        return 0.0

    @classmethod
    def wrap(
        cls,
        label: str = "",
        log_level: int = logging.DEBUG,
    ) -> Callable:
        """Decorator factory that wraps a function with timing."""
        def decorator(fn: Callable) -> Callable:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with cls(label or fn.__name__, log_level=log_level):
                    return fn(*args, **kwargs)
            return wrapper
        return decorator


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def log_performance(
    label: str,
    elapsed_s: float,
    extra: Optional[Dict[str, Any]] = None,
    level: int = logging.DEBUG,
) -> None:
    """Write a structured performance log entry.

    Parameters
    ----------
    label : str
        Human-readable label for this measurement.
    elapsed_s : float
        Measured elapsed time in seconds.
    extra : dict | None
        Additional key-value pairs to include in the log message.
    level : int
        Python logging level (default DEBUG).
    """
    parts = [f"[PERF] {label}: {format_elapsed(elapsed_s)}"]
    if extra:
        parts += [f"{k}={v}" for k, v in extra.items()]
    log.log(level, "  ".join(parts))


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_elapsed(seconds: float) -> str:
    """Return *seconds* as a human-readable string.

    Examples
    --------
    >>> format_elapsed(0.045)
    '45.0 ms'
    >>> format_elapsed(3.7)
    '3.70 s'
    >>> format_elapsed(125.4)
    '2m 5s'
    """
    if seconds < 1.0:
        return f"{seconds * 1000:.1f} ms"
    if seconds < 60.0:
        return f"{seconds:.2f} s"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}m {secs}s"


def timed(label: str = "") -> Callable:
    """Simple timing decorator (alias for PerformanceMonitor.wrap)."""
    return PerformanceMonitor.wrap(label=label)