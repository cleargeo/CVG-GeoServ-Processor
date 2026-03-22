# -*- coding: utf-8 -*-
# =============================================================================
# (c) Clearview Geographic LLC -- All Rights Reserved | Est. 2018
# Proprietary Software -- Internal Use Only
# =============================================================================
"""GeoServ Processor — Checkpoint/recovery system.

Saves job progress so failed multi-job runs can be resumed without reprocessing
already-completed jobs.

Usage::

    from geoserv_processor.recovery import RecoveryManager

    rm = RecoveryManager(recovery_dir="/tmp/geoserv_recovery", project_name="my_proj")
    rm.load()                        # load existing checkpoint if present

    for i, job in enumerate(jobs):
        if rm.is_done(i):
            print(f"Job {i} already complete, skipping")
            continue
        run_job(job)
        rm.mark_done(i, output_path=job.output.path)

"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_CHECKPOINT_FILENAME = "geoserv_checkpoint.json"


class RecoveryManager:
    """Persist job completion state to a JSON checkpoint file."""

    def __init__(
        self,
        recovery_dir: Optional[str],
        project_name: str = "geoserv",
    ) -> None:
        if recovery_dir:
            self._dir = Path(recovery_dir)
            self._dir.mkdir(parents=True, exist_ok=True)
            self._path = self._dir / _CHECKPOINT_FILENAME
        else:
            self._dir = None
            self._path = None
        self._project = project_name
        self._state: Dict[str, Any] = {
            "project": project_name,
            "created": datetime.now(timezone.utc).isoformat(),
            "updated": datetime.now(timezone.utc).isoformat(),
            "completed_jobs": {},
        }

    # ------------------------------------------------------------------
    def load(self) -> bool:
        """Load checkpoint from disk.  Returns True if checkpoint was found."""
        if self._path is None or not self._path.exists():
            return False
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                saved = json.load(fh)
            self._state.update(saved)
            n = len(self._state.get("completed_jobs", {}))
            log.info("[Recovery] Loaded checkpoint: %d completed job(s) from %s", n, self._path)
            return True
        except Exception as exc:
            log.warning("[Recovery] Could not load checkpoint (%s) — starting fresh.", exc)
            return False

    def save(self) -> None:
        """Persist current state to disk."""
        if self._path is None:
            return
        self._state["updated"] = datetime.now(timezone.utc).isoformat()
        try:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, indent=2, default=str)
        except Exception as exc:
            log.warning("[Recovery] Could not save checkpoint: %s", exc)

    # ------------------------------------------------------------------
    def is_done(self, job_idx: int) -> bool:
        return str(job_idx) in self._state.get("completed_jobs", {})

    def mark_done(
        self,
        job_idx: int,
        output_path: Optional[str] = None,
        elapsed_s: float = 0.0,
    ) -> None:
        self._state.setdefault("completed_jobs", {})[str(job_idx)] = {
            "output_path": output_path,
            "elapsed_s": round(elapsed_s, 2),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save()
        log.info("[Recovery] Job %d marked complete → %s", job_idx, output_path)

    def completed_jobs(self) -> List[int]:
        return [int(k) for k in self._state.get("completed_jobs", {}).keys()]

    def reset(self) -> None:
        """Delete the checkpoint and reset state."""
        self._state["completed_jobs"] = {}
        if self._path and self._path.exists():
            self._path.unlink()
        log.info("[Recovery] Checkpoint reset.")
