#!/usr/bin/env python3
"""
Phase D test (part 2): Autonomous Scheduler

Proves the background scheduler actually re-optimizes and applies
decisions on its own, without a human calling
POST /optimization/optimize/{id}/apply for every workflow.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent / "app"))

import asyncio

from app.services.metrics_aggregator import MetricsAggregator, MetricPoint, MetricType
from app.services.optimization_engine import OptimizationEngine
from app.services.scheduler import AutonomousScheduler


def seed_declining_workflow(aggregator: MetricsAggregator, tenant_id: str, workflow_id: str):
    """Same shape as test_phase_b.py's decline-001 - reliably produces a PAUSE decision"""
    now = datetime.utcnow()
    for hour in range(24):
        ts = now - timedelta(hours=24 - hour)
        aggregator.add_metric(MetricPoint(
            timestamp=ts, metric_type=MetricType.VIEWS, value=max(100, 1000 - hour * 40),
            engine="marketing", workflow_id=workflow_id, tenant_id=tenant_id
        ))
        aggregator.add_metric(MetricPoint(
            timestamp=ts, metric_type=MetricType.CONVERSIONS, value=max(0, 30 - hour),
            engine="analytics", workflow_id=workflow_id, tenant_id=tenant_id
        ))


def seed_scaling_workflow(aggregator: MetricsAggregator, tenant_id: str, workflow_id: str):
    """Same shape as test_phase_b.py's pillar-001 - reliably produces a SCALE_BUDGET decision"""
    now = datetime.utcnow()
    for hour in range(24):
        ts = now - timedelta(hours=24 - hour)
        aggregator.add_metric(MetricPoint(
            timestamp=ts, metric_type=MetricType.VIEWS, value=1000 + hour * 50,
            engine="marketing", workflow_id=workflow_id, tenant_id=tenant_id
        ))
        aggregator.add_metric(MetricPoint(
            timestamp=ts, metric_type=MetricType.CONVERSIONS, value=60 + hour * 2,
            engine="analytics", workflow_id=workflow_id, tenant_id=tenant_id
        ))


async def test_tick_applies_across_tenants():
    print("\n" + "=" * 70)
    print("Phase D Scheduler Test 1: One tick, two tenants, two outcomes")
    print("=" * 70)

    aggregator = MetricsAggregator()
    engine = OptimizationEngine(aggregator)

    seed_declining_workflow(aggregator, "tenant-x", "wf-pause")
    seed_scaling_workflow(aggregator, "tenant-y", "wf-scale")

    active_workflows = {
        "tenant-x": {"wf-pause": {"id": "wf-pause", "status": "active", "applied_decisions": []}},
        "tenant-y": {"wf-scale": {"id": "wf-scale", "status": "active", "applied_decisions": []}},
    }

    scheduler = AutonomousScheduler(
        optimization_engine=engine,
        engine_urls={},  # no real engines - SCALE_BUDGET will report "failed", which is fine
        get_active_workflows=lambda: active_workflows,
        interval_seconds=9999,
    )

    summary = await scheduler.tick()

    assert summary.tenants_processed == 2
    assert summary.workflows_processed == 2
    assert scheduler.tick_count == 1

    assert active_workflows["tenant-x"]["wf-pause"]["status"] == "paused"
    assert len(active_workflows["tenant-x"]["wf-pause"]["applied_decisions"]) == 1

    assert active_workflows["tenant-y"]["wf-scale"]["status"] == "active", "SCALE_BUDGET must not touch status"
    assert len(active_workflows["tenant-y"]["wf-scale"]["applied_decisions"]) == 1
    scale_result = active_workflows["tenant-y"]["wf-scale"]["applied_decisions"][0]["result"]
    assert scale_result["status"] == "failed"  # no engine registered - reported, not raised
    assert scale_result["engine_called"] == "marketing"

    print(f"\n[OK] One tick processed 2 tenants / 2 workflows")
    print(f"[OK] tenant-x's declining workflow -> paused locally")
    print(f"[OK] tenant-y's scaling workflow -> engine call attempted, reported failed (no engine registered)")
    print(f"[OK] Both workflows got an applied_decisions audit entry")


async def test_start_stop_ticks_on_interval():
    print("\n" + "=" * 70)
    print("Phase D Scheduler Test 2: start()/stop() actually run on a timer")
    print("=" * 70)

    engine = OptimizationEngine(MetricsAggregator())
    scheduler = AutonomousScheduler(
        optimization_engine=engine, engine_urls={},
        get_active_workflows=lambda: {},  # nothing to process, just proving ticks happen
        interval_seconds=0.05,
    )

    scheduler.start()
    assert scheduler.running is True

    await asyncio.sleep(0.3)
    ticks_seen = scheduler.tick_count
    assert ticks_seen >= 3, f"Expected several ticks in 0.3s at 0.05s interval, got {ticks_seen}"

    await scheduler.stop()
    assert scheduler.running is False

    await asyncio.sleep(0.15)
    assert scheduler.tick_count == ticks_seen, "Ticking must actually stop after stop()"

    print(f"\n[OK] Scheduler ticked {ticks_seen} times in ~0.3s at a 0.05s interval")
    print(f"[OK] stop() halts ticking (count unchanged after stop)")


async def test_pause_resume_halts_and_restarts_application():
    print("\n" + "=" * 70)
    print("Phase D Scheduler Test 3: pause()/resume() gate ticking without killing the loop")
    print("=" * 70)

    engine = OptimizationEngine(MetricsAggregator())
    scheduler = AutonomousScheduler(
        optimization_engine=engine, engine_urls={},
        get_active_workflows=lambda: {},
        interval_seconds=0.05,
    )

    scheduler.start()
    scheduler.pause()

    await asyncio.sleep(0.2)
    assert scheduler.tick_count == 0, "Paused scheduler must not tick"
    assert scheduler.running is True, "Pausing must not kill the background task"

    scheduler.resume()
    await asyncio.sleep(0.2)
    assert scheduler.tick_count >= 1, "Resumed scheduler must start ticking again"

    await scheduler.stop()
    print(f"\n[OK] Paused scheduler stayed running but applied 0 ticks")
    print(f"[OK] Resuming let it start ticking again ({scheduler.tick_count} ticks)")


def test_scheduler_http_endpoints():
    print("\n" + "=" * 70)
    print("Phase D Scheduler Test 4: HTTP status/pause/resume")
    print("=" * 70)

    from main import app
    from fastapi.testclient import TestClient
    from app.services.tenancy import ADMIN_KEY

    with TestClient(app) as client:
        resp = client.get("/scheduler/status")
        assert resp.status_code == 200, resp.text
        status = resp.json()
        assert status["running"] is True
        assert status["paused"] is False

        resp = client.post("/scheduler/pause")
        assert resp.status_code == 401, "Pause without admin key must be rejected"

        resp = client.post("/scheduler/pause", headers={"X-Admin-Key": ADMIN_KEY})
        assert resp.status_code == 200, resp.text
        assert client.get("/scheduler/status").json()["paused"] is True

        resp = client.post("/scheduler/resume", headers={"X-Admin-Key": ADMIN_KEY})
        assert resp.status_code == 200, resp.text
        assert client.get("/scheduler/status").json()["paused"] is False

        print(f"\n[OK] GET /scheduler/status is public and reports running=True on a live app")
        print(f"[OK] POST /scheduler/pause without admin key -> 401")
        print(f"[OK] Admin pause/resume correctly flips status.paused")


def main():
    print("\n" + "=" * 70)
    print("OS42 Phase D (part 2): Autonomous Scheduler")
    print("=" * 70)

    try:
        asyncio.run(test_tick_applies_across_tenants())
        asyncio.run(test_start_stop_ticks_on_interval())
        asyncio.run(test_pause_resume_halts_and_restarts_application())
        test_scheduler_http_endpoints()

        print("\n" + "=" * 70)
        print("[OK] PHASE D SCHEDULER TEST COMPLETE - Autonomous triggering works")
        print("=" * 70 + "\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Phase D scheduler test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
