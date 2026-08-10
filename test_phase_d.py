#!/usr/bin/env python3
"""
Phase D test: Decision Execution (closing the recommend -> act loop)

Part 1 (service layer): drives DecisionExecutor directly.
  - PAUSE/RESUME mutate local workflow state, no engine call involved
  - Engine-owned actions (e.g. SCALE_BUDGET) call the mapped engine; a
    fake in-process ASGI "engine" proves the right endpoint/payload is
    used, and a deliberately unreachable engine proves failures are
    reported gracefully instead of raised
Part 2 (HTTP layer): drives the real POST /optimization/optimize/{id}/apply
  endpoint end-to-end via TestClient, including against engines that are
  not actually running (as in a real dev environment) - the point being
  that the loop closes without crashing either way, and the workflow's
  audit trail (applied_decisions) reflects what actually happened.
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / "app"))

import httpx
from fastapi import FastAPI, Request

from app.services.decision_executor import DecisionExecutor
from app.services.metrics_aggregator import OptimizationAction
from app.services.optimization_engine import OptimizationDecision


TENANT = "phase-d-tenant"


# ---------------------------------------------------------------------------
# Part 1: DecisionExecutor (service layer)
# ---------------------------------------------------------------------------

def build_fake_engine():
    """A minimal in-process ASGI 'engine' that records what it receives"""
    app = FastAPI()
    received = []

    @app.post("/scale_budget")
    async def scale_budget(request: Request):
        body = await request.json()
        received.append(("scale_budget", body))
        return {"status": "ok"}

    return app, received


async def test_pause_resume_local_state():
    print("\n" + "=" * 70)
    print("Phase D Test 1: PAUSE/RESUME apply directly to local state")
    print("=" * 70)

    executor = DecisionExecutor(engine_urls={})
    workflow = {"id": "wf-1", "status": "active"}

    pause_decision = OptimizationDecision(
        workflow_id="wf-1", tenant_id=TENANT, timestamp=datetime.utcnow(),
        action=OptimizationAction.PAUSE, reason="test", confidence=0.9
    )
    result = await executor.apply(pause_decision, workflow)
    assert workflow["status"] == "paused", "PAUSE must flip workflow status locally"
    assert result.status == "applied"
    assert result.engine_called is None, "PAUSE must never call an engine"

    resume_decision = OptimizationDecision(
        workflow_id="wf-1", tenant_id=TENANT, timestamp=datetime.utcnow(),
        action=OptimizationAction.RESUME, reason="test", confidence=0.9
    )
    result = await executor.apply(resume_decision, workflow)
    assert workflow["status"] == "active", "RESUME must flip workflow status back"
    assert result.status == "applied"

    # No workflow record at all - must not crash
    result = await executor.apply(pause_decision, None)
    assert result.status == "applied"
    assert "No local workflow record" in result.detail

    await executor.aclose()
    print("\n[OK] PAUSE marks workflow paused, RESUME marks it active")
    print("[OK] Neither action calls an engine")
    print("[OK] Missing workflow record handled without crashing")


async def test_engine_call_success():
    print("\n" + "=" * 70)
    print("Phase D Test 2: Engine-owned action calls the right engine")
    print("=" * 70)

    fake_app, received = build_fake_engine()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=fake_app), base_url="http://fake")

    executor = DecisionExecutor(engine_urls={"marketing": "http://fake"}, client=client)

    decision = OptimizationDecision(
        workflow_id="wf-2", tenant_id=TENANT, timestamp=datetime.utcnow(),
        action=OptimizationAction.SCALE_BUDGET, reason="high conversion", confidence=0.9,
        estimated_impact=0.3, parameters={"budget_increase_percent": 50}
    )
    result = await executor.apply(decision, workflow=None)

    assert result.status == "applied", result.detail
    assert result.engine_called == "marketing"
    assert len(received) == 1
    action_name, body = received[0]
    assert action_name == "scale_budget"
    assert body["workflow_id"] == "wf-2"
    assert body["tenant_id"] == TENANT
    assert body["budget_increase_percent"] == 50

    await executor.aclose()
    print(f"\n[OK] SCALE_BUDGET routed to marketing/scale_budget")
    print(f"[OK] Payload carried workflow_id, tenant_id, and decision parameters: {body}")


async def test_engine_call_failure_is_graceful():
    print("\n" + "=" * 70)
    print("Phase D Test 3: Unreachable engine fails gracefully, doesn't raise")
    print("=" * 70)

    # Port 1 is reserved/unused - nothing will ever answer here.
    executor = DecisionExecutor(engine_urls={"marketing": "http://127.0.0.1:1"})

    decision = OptimizationDecision(
        workflow_id="wf-3", tenant_id=TENANT, timestamp=datetime.utcnow(),
        action=OptimizationAction.SCALE_BUDGET, reason="high conversion", confidence=0.9,
        parameters={"budget_increase_percent": 50}
    )
    result = await executor.apply(decision, workflow=None)

    assert result.status == "failed", "Unreachable engine must report failure, not raise"
    assert result.engine_called == "marketing"
    assert "failed" in result.detail.lower()

    await executor.aclose()
    print(f"\n[OK] Unreachable engine reported as status=failed: {result.detail}")


# ---------------------------------------------------------------------------
# Part 2: HTTP layer (full app, real endpoint)
# ---------------------------------------------------------------------------

def test_apply_endpoint_http():
    print("\n" + "=" * 70)
    print("Phase D Test 4: POST /optimization/optimize/{id}/apply over HTTP")
    print("=" * 70)

    from main import app
    from fastapi.testclient import TestClient
    from app.services.tenancy import ADMIN_KEY

    with TestClient(app) as client:
        resp = client.post(
            "/tenants",
            params={"name": "Phase D HTTP Tenant", "tenant_id": "phase-d-http-tenant"},
            headers={"X-Admin-Key": ADMIN_KEY},
        )
        assert resp.status_code == 200, resp.text
        headers = {"X-API-Key": resp.json()["api_key"]}

        # --- Declining workflow -> PAUSE, applied purely locally ---
        pause_wf_id = "d-pause-001"
        resp = client.post("/workflows/create", params={"workflow_id": pause_wf_id}, json={"steps": []}, headers=headers)
        assert resp.status_code == 200, resp.text

        now = datetime.utcnow()
        for hour in range(24):
            client.post(
                "/optimization/metrics/record",
                params={"workflow_id": pause_wf_id, "metric_type": "views", "value": max(100, 1000 - hour * 40), "engine": "marketing"},
                headers=headers,
            )
            client.post(
                "/optimization/metrics/record",
                params={"workflow_id": pause_wf_id, "metric_type": "conversions", "value": max(0, 30 - hour), "engine": "analytics"},
                headers=headers,
            )

        resp = client.post(f"/optimization/optimize/{pause_wf_id}/apply", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["decision"]["action"] == "pause", body["decision"]
        assert body["execution"]["status"] == "applied"
        assert body["execution"]["engine_called"] is None

        resp = client.get(f"/workflows/{pause_wf_id}", headers=headers)
        workflow = resp.json()
        assert workflow["status"] == "paused", "Workflow record must reflect the PAUSE"
        assert len(workflow["applied_decisions"]) == 1

        print(f"\n[OK] Declining workflow -> PAUSE decision applied, workflow status='paused'")
        print(f"[OK] applied_decisions audit trail recorded on the workflow record")

        # --- High-conversion workflow -> SCALE_BUDGET, engine unreachable in this env ---
        scale_wf_id = "d-scale-001"
        resp = client.post("/workflows/create", params={"workflow_id": scale_wf_id}, json={"steps": []}, headers=headers)
        assert resp.status_code == 200, resp.text

        for hour in range(24):
            client.post(
                "/optimization/metrics/record",
                params={"workflow_id": scale_wf_id, "metric_type": "views", "value": 1000 + hour * 50, "engine": "marketing"},
                headers=headers,
            )
            client.post(
                "/optimization/metrics/record",
                params={"workflow_id": scale_wf_id, "metric_type": "conversions", "value": 60 + hour * 2, "engine": "analytics"},
                headers=headers,
            )

        resp = client.post(f"/optimization/optimize/{scale_wf_id}/apply", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["decision"]["action"] == "scale_budget", body["decision"]
        # No real marketing engine is running in this dev environment -
        # the point of this test is that the endpoint still returns 200
        # with a clear failure reason instead of raising.
        assert body["execution"]["status"] == "failed"
        assert body["execution"]["engine_called"] == "marketing"

        print(f"\n[OK] High-conversion workflow -> SCALE_BUDGET decision generated")
        print(f"[OK] Engine unreachable -> execution.status='failed', endpoint still returned 200")
        print(f"     detail: {body['execution']['detail']}")

        # --- Applying against a workflow_id with no /workflows/create call at all ---
        resp = client.post("/optimization/optimize/never-created-001/apply", headers=headers)
        assert resp.status_code == 200, resp.text
        print(f"\n[OK] Apply against an unregistered workflow_id doesn't crash (workflow=None path)")


def main():
    print("\n" + "=" * 70)
    print("OS42 Phase D: Decision Execution")
    print("=" * 70)

    try:
        import asyncio
        asyncio.run(test_pause_resume_local_state())
        asyncio.run(test_engine_call_success())
        asyncio.run(test_engine_call_failure_is_graceful())
        test_apply_endpoint_http()

        print("\n" + "=" * 70)
        print("[OK] PHASE D TEST COMPLETE - Decision execution loop closes end-to-end")
        print("=" * 70 + "\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Phase D test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
