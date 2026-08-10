#!/usr/bin/env python3
"""
Phase D test (part 3): Persistence

Proves state actually survives a process restart when
OS42_PERSISTENCE_PATH is set, and that persistence is a true no-op when
unset (every prior-phase test doesn't set it, so this must not change
their behavior at all).

This spawns genuinely separate Python subprocesses for the "before" and
"after" sides of each round trip - not just two objects in the same
process, which would share already-populated state and prove nothing
about surviving a real restart. This file is both the test runner (no
args) and, via --write/--read/--http-write/--http-read, the subprocess
entry points it spawns.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent


# ---------------------------------------------------------------------------
# Subprocess entry points
# ---------------------------------------------------------------------------

def run_writer(snapshot_path: str):
    """Fresh process: build state directly against the service layer, save it"""
    sys.path.insert(0, str(REPO_ROOT / "app"))
    from datetime import datetime

    from app.services.metrics_aggregator import MetricsAggregator, MetricPoint, MetricType
    from app.services.optimization_engine import OptimizationEngine
    from app.services.tenancy import TenantRegistry
    from app.services.persistence import save_snapshot

    registry = TenantRegistry()
    tenant = registry.register(name="Persistence Test Co", tenant_id="persist-tenant")

    aggregator = MetricsAggregator()
    aggregator.add_metric(MetricPoint(
        timestamp=datetime.utcnow(), metric_type=MetricType.VIEWS, value=500,
        engine="marketing", workflow_id="persist-wf", tenant_id=tenant.tenant_id
    ))

    engine = OptimizationEngine(aggregator)
    decision = engine.analyze_and_optimize("persist-wf", 24, tenant_id=tenant.tenant_id)

    active_workflows = {
        tenant.tenant_id: {"persist-wf": {"id": "persist-wf", "status": "active", "applied_decisions": []}}
    }

    saved_path = save_snapshot(registry, aggregator, engine, active_workflows, path=snapshot_path)
    assert saved_path == snapshot_path

    print(json.dumps({
        "tenant_id": tenant.tenant_id, "api_key": tenant.api_key,
        "decision_action": decision.action.value,
    }))


def run_reader(snapshot_path: str):
    """A genuinely different process: brand-new empty singletons, load the snapshot"""
    sys.path.insert(0, str(REPO_ROOT / "app"))
    from app.services.metrics_aggregator import MetricsAggregator
    from app.services.optimization_engine import OptimizationEngine
    from app.services.tenancy import TenantRegistry
    from app.services.persistence import load_snapshot

    registry = TenantRegistry()
    aggregator = MetricsAggregator()
    engine = OptimizationEngine(aggregator)
    active_workflows = {}

    restored = load_snapshot(registry, aggregator, engine, active_workflows, path=snapshot_path)
    assert restored is True

    tenant = registry.get("persist-tenant")
    assert tenant is not None, "Tenant must survive the restart"

    metrics = aggregator.get_metrics("persist-wf", tenant_id="persist-tenant")
    assert len(metrics) == 1, "Metric must survive the restart"

    history = engine.get_execution_history("persist-wf", tenant_id="persist-tenant")
    assert len(history) == 1, "Decision must survive the restart"

    assert "persist-tenant" in active_workflows
    assert "persist-wf" in active_workflows["persist-tenant"]

    print(json.dumps({
        "tenant_id": tenant.tenant_id, "api_key": tenant.api_key,
        "metric_count": len(metrics), "decision_action": history[0].action.value,
    }))


def run_http_writer(snapshot_path: str):
    """Fresh process: create state through the real HTTP API with persistence enabled"""
    import os
    os.environ["OS42_PERSISTENCE_PATH"] = snapshot_path
    sys.path.insert(0, str(REPO_ROOT / "app"))

    from main import app
    from fastapi.testclient import TestClient
    from app.services.tenancy import ADMIN_KEY

    with TestClient(app) as client:
        resp = client.post(
            "/tenants", params={"name": "HTTP Persist Tenant", "tenant_id": "http-persist-tenant"},
            headers={"X-Admin-Key": ADMIN_KEY},
        )
        assert resp.status_code == 200, resp.text
        tenant = resp.json()
        headers = {"X-API-Key": tenant["api_key"]}

        resp = client.post("/workflows/create", params={"workflow_id": "http-persist-wf"}, json={"steps": []}, headers=headers)
        assert resp.status_code == 200, resp.text

        resp = client.post(
            "/optimization/metrics/record",
            params={"workflow_id": "http-persist-wf", "metric_type": "views", "value": 500, "engine": "marketing"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
    # `with` block exit -> lifespan shutdown -> save_snapshot()

    print(json.dumps({"tenant_id": tenant["tenant_id"], "api_key": tenant["api_key"]}))


def run_http_reader(snapshot_path: str, api_key: str):
    """A genuinely different process: fresh app singletons, same snapshot file"""
    import os
    os.environ["OS42_PERSISTENCE_PATH"] = snapshot_path
    sys.path.insert(0, str(REPO_ROOT / "app"))

    from main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/workflows", headers={"X-API-Key": api_key})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1, f"Expected the restored workflow, got {body}"
        assert body["active_workflows"][0]["id"] == "http-persist-wf"

    print(json.dumps({"ok": True}))


# ---------------------------------------------------------------------------
# Test runner (parent process)
# ---------------------------------------------------------------------------

def _run_subprocess(*args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, __file__, *args],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_snapshot_survives_a_real_process_restart():
    print("\n" + "=" * 70)
    print("Phase D Persistence Test 1: Service layer survives an actual process restart")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmp:
        snapshot_path = str(Path(tmp) / "snapshot.json")

        written = _run_subprocess("--write", snapshot_path)
        assert Path(snapshot_path).exists(), "Snapshot file must exist after save_snapshot()"

        read_back = _run_subprocess("--read", snapshot_path)

        assert read_back["tenant_id"] == written["tenant_id"]
        assert read_back["api_key"] == written["api_key"], "API key must round-trip exactly"
        assert read_back["decision_action"] == written["decision_action"]
        assert read_back["metric_count"] == 1

    print(f"\n[OK] Process A wrote tenant '{written['tenant_id']}', 1 metric, decision={written['decision_action']}")
    print(f"[OK] Process B (fresh, empty singletons) loaded the exact same state from disk")


def test_http_lifecycle_survives_a_real_restart():
    print("\n" + "=" * 70)
    print("Phase D Persistence Test 2: Full HTTP lifecycle survives an actual restart")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmp:
        snapshot_path = str(Path(tmp) / "http_snapshot.json")

        written = _run_subprocess("--http-write", snapshot_path)
        result = _run_subprocess("--http-read", snapshot_path, written["api_key"])
        assert result["ok"] is True

    print(f"\n[OK] Tenant + workflow + metric created over HTTP in process A...")
    print(f"[OK] ...visible over HTTP in a completely fresh process B, using the same API key")


def test_disabled_by_default_is_a_true_no_op():
    print("\n" + "=" * 70)
    print("Phase D Persistence Test 3: Disabled by default (no env var) touches nothing")
    print("=" * 70)

    sys.path.insert(0, str(REPO_ROOT / "app"))
    from app.services.metrics_aggregator import MetricsAggregator
    from app.services.optimization_engine import OptimizationEngine
    from app.services.tenancy import TenantRegistry
    from app.services import persistence

    assert persistence.PERSISTENCE_PATH is None, "Default must be disabled unless explicitly configured"

    registry = TenantRegistry()
    aggregator = MetricsAggregator()
    engine = OptimizationEngine(aggregator)

    assert persistence.save_snapshot(registry, aggregator, engine, {}) is None, \
        "save_snapshot() must no-op when persistence is disabled"
    assert persistence.load_snapshot(registry, aggregator, engine, {}) is False, \
        "load_snapshot() must no-op when persistence is disabled"

    print(f"\n[OK] PERSISTENCE_PATH is None by default")
    print(f"[OK] save_snapshot()/load_snapshot() are true no-ops with nothing configured")


def main():
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode == "--write":
            return run_writer(sys.argv[2])
        if mode == "--read":
            return run_reader(sys.argv[2])
        if mode == "--http-write":
            return run_http_writer(sys.argv[2])
        if mode == "--http-read":
            return run_http_reader(sys.argv[2], sys.argv[3])
        raise SystemExit(f"Unknown mode: {mode}")

    print("\n" + "=" * 70)
    print("OS42 Phase D (part 3): Persistence")
    print("=" * 70)

    try:
        test_snapshot_survives_a_real_process_restart()
        test_http_lifecycle_survives_a_real_restart()
        test_disabled_by_default_is_a_true_no_op()

        print("\n" + "=" * 70)
        print("[OK] PHASE D PERSISTENCE TEST COMPLETE - State survives a real restart")
        print("=" * 70 + "\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Phase D persistence test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = main()
    if result is False:
        sys.exit(1)
