# -*- coding: utf-8 -*-
"""Tests for geoserv_processor.monitoring"""
import time
import pytest
from geoserv_processor.monitoring import (
    ResourceSnapshot,
    StepTimer,
    PerformanceMonitor,
    format_elapsed,
    log_performance,
    timed,
)


class TestFormatElapsed:
    def test_milliseconds(self):
        s = format_elapsed(0.045)
        assert "ms" in s

    def test_seconds(self):
        s = format_elapsed(3.7)
        assert "s" in s
        assert "ms" not in s

    def test_minutes(self):
        s = format_elapsed(125.0)
        assert "m" in s


class TestResourceSnapshot:
    def test_capture_returns_instance(self):
        snap = ResourceSnapshot.capture()
        assert isinstance(snap, ResourceSnapshot)
        assert snap.timestamp > 0

    def test_delta(self):
        snap1 = ResourceSnapshot(rss_mb=100.0)
        snap2 = ResourceSnapshot(rss_mb=150.0)
        assert snap2.delta_mb(snap1) == pytest.approx(50.0)

class TestStepTimer:
    def test_basic_step(self):
        timer = StepTimer("test_pipeline")
        with timer.step("step1"):
            time.sleep(0.01)
        steps = timer.steps()
        assert len(steps) == 1
        assert steps[0]["step"] == "step1"
        assert steps[0]["elapsed_s"] >= 0.005

    def test_multiple_steps(self):
        timer = StepTimer("multi")
        with timer.step("a"):
            pass
        with timer.step("b"):
            pass
        assert len(timer.steps()) == 2

    def test_summary_contains_pipeline_name(self):
        timer = StepTimer("my_pipe")
        with timer.step("x"):
            pass
        summary = timer.summary()
        assert "my_pipe" in summary
        assert "TOTAL" in summary

    def test_to_dict(self):
        timer = StepTimer("pipe")
        with timer.step("step"):
            pass
        d = timer.to_dict()
        assert "pipeline" in d
        assert "steps" in d
        assert "total_elapsed_s" in d

class TestPerformanceMonitor:
    def test_context_manager(self):
        with PerformanceMonitor("test_block") as mon:
            time.sleep(0.01)
        assert mon.elapsed_s >= 0.005

    def test_wrap_decorator(self):
        @PerformanceMonitor.wrap("my_func")
        def my_func(x):
            return x * 2

        result = my_func(5)
        assert result == 10

    def test_timed_alias(self):
        @timed("aliased")
        def fn():
            return 42

        assert fn() == 42
