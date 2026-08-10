#!/usr/bin/env python3
"""
Phase E test: Workflow Execution

Since Phase A, WorkflowExecutor has existed with a full implementation
(sequential step execution, $steps.x.y parameter resolution, on_error
handling) but was never actually wired into the live HTTP API -
POST /workflows/create only ever stored metadata. This is the first test
to exercise the real WorkflowExecutor.execute_workflow() end-to-end
(every prior "end-to-end" test hand-simulated engine responses without
touching WorkflowExecutor or httpx at all).

Part 1 (service layer): WorkflowExecutor against a fake in-process ASGI
  engine - proves parameter resolution and on_error handling actually
  work through the real code path.
Part 2 (HTTP layer): the new POST /workflows/{id}/execute endpoint,
  including against the real (unreachable) ENGINE_URLS, and proving
  execution never disturbs the separate pause/resume lifecycle status.
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / "app"))

import asyncio
import httpx
from fastapi import FastAPI, HTTPException, Request

from app.services.workflow_executor import WorkflowExecutor


# ---------------------------------------------------------------------------
# Part 1: WorkflowExecutor (service layer)
# ---------------------------------------------------------------------------

def build_fake_engine():
    """A minimal in-process ASGI 'content engine' that records what it receives"""
    app = FastAPI()
    received = []

    @app.post("/create")
    async def create(request: Request):
        body = await request.json()
        received.append(("create", body))
        return {"id": "content-001", "title": body.get("title", "untitled")}

    @app.post("/repurpose")
    async def repurpose(request: Request):
        body = await request.json()
        received.append(("repurpose", body))
        return {"formats": ["twitter", "linkedin"], "source_id": body.get("content_id")}

    @app.post("/always_fails")
    async def always_fails(request: Request):
        received.append(("always_fails", await request.json()))
        raise HTTPException(status_code=500, detail="engine exploded")

    return app, received


def make_executor(received_holder=None):
    fake_app, received = build_fake_engine()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=fake_app), base_url="http://fake")
    return WorkflowExecutor(engine_urls={"content": "http://fake"}, client=client), received


async def test_multi_step_workflow_with_parameter_resolution():
    print("\n" + "=" * 70)
    print("Phase E Test 1: Multi-step execution with $steps.x.y parameter resolution")
    print("=" * 70)

    executor, received = make_executor()
    await executor.connect()

    definition = {
        "steps": [
            {"id": "create_pillar", "engine": "content", "action": "create",
             "params": {"title": "AI Guide"}, "on_error": "stop"},
            {"id": "repurpose", "engine": "content", "action": "repurpose",
             "params": {"content_id": "$steps.create_pillar.id"}, "on_error": "stop"},
        ]
    }

    result = await executor.execute_workflow("wf-exec-1", definition)
    await executor.disconnect()

    assert result["status"] == "completed", result
    assert result["steps"] == 2
    assert result["results"]["create_pillar"]["id"] == "content-001"
    assert result["results"]["repurpose"]["source_id"] == "content-001", \
        "Step 2's content_id must have been resolved from step 1's real output"

    assert received[0] == ("create", {"title": "AI Guide"})
    assert received[1][0] == "repurpose" and received[1][1]["content_id"] == "content-001"

    print(f"\n[OK] Step 1 created content-001")
    print(f"[OK] Step 2's $steps.create_pillar.id resolved to the real value and reached the engine")


async def test_step_failure_with_continue_does_not_abort_workflow():
    print("\n" + "=" * 70)
    print("Phase E Test 2: on_error='continue' lets the workflow finish despite a failed step")
    print("=" * 70)

    executor, _ = make_executor()
    await executor.connect()

    definition = {
        "steps": [
            {"id": "boom", "engine": "content", "action": "always_fails", "params": {}, "on_error": "continue"},
            {"id": "create_pillar", "engine": "content", "action": "create", "params": {"title": "still runs"}, "on_error": "stop"},
        ]
    }
    result = await executor.execute_workflow("wf-exec-2", definition)
    await executor.disconnect()

    assert result["status"] == "completed", result
    assert result["results"]["boom"]["status"] == "failed"
    assert result["results"]["create_pillar"]["id"] == "content-001"

    print(f"\n[OK] Failed step recorded as {{'status': 'failed', ...}}, workflow still completed")
    print(f"[OK] Step 2 ran normally after step 1's failure")


async def test_step_failure_with_stop_aborts_workflow():
    print("\n" + "=" * 70)
    print("Phase E Test 3: on_error='stop' (the default) aborts the whole workflow")
    print("=" * 70)

    executor, _ = make_executor()
    await executor.connect()

    definition = {
        "steps": [
            {"id": "boom", "engine": "content", "action": "always_fails", "params": {}, "on_error": "stop"},
            {"id": "never_runs", "engine": "content", "action": "create", "params": {}, "on_error": "stop"},
        ]
    }
    result = await executor.execute_workflow("wf-exec-3", definition)
    await executor.disconnect()

    assert result["status"] == "failed", result
    assert "never_runs" not in result["results"]

    print(f"\n[OK] Workflow status='failed', second step never ran")


# ---------------------------------------------------------------------------
# Part 2: HTTP layer (real endpoint, real ENGINE_URLS)
# ---------------------------------------------------------------------------

def test_http_execute_lifecycle():
    print("\n" + "=" * 70)
    print("Phase E Test 4: POST /workflows/{id}/execute over HTTP")
    print("=" * 70)

    from main import app
    from fastapi.testclient import TestClient
    from app.services.tenancy import ADMIN_KEY

    with TestClient(app) as client:
        resp = client.post(
            "/tenants", params={"name": "Exec Tenant", "tenant_id": "exec-tenant"},
            headers={"X-Admin-Key": ADMIN_KEY},
        )
        assert resp.status_code == 200, resp.text
        headers = {"X-API-Key": resp.json()["api_key"]}

        resp = client.post("/workflows/never-created/execute", headers=headers)
        assert resp.status_code == 404, "Executing an unregistered workflow_id must 404"

        resp = client.post(
            "/workflows/create", params={"workflow_id": "http-exec-wf"},
            json={"steps": [{"id": "s1", "engine": "content", "action": "create", "params": {}, "on_error": "stop"}]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

        resp = client.post("/workflows/http-exec-wf/execute", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # No real content-engine is running in this dev environment - the
        # point is the endpoint still returns 200 with a clear failure
        # reason instead of raising, same philosophy as Phase D's apply.
        assert body["execution"]["status"] == "failed"

        resp = client.get("/workflows/http-exec-wf", headers=headers)
        workflow = resp.json()
        assert workflow["status"] == "pending", "status is the pause/resume lifecycle field, untouched by execution"
        assert workflow["last_execution"]["status"] == "failed"

        print(f"\n[OK] Executing an unregistered workflow_id -> 404")
        print(f"[OK] Executing against unreachable engines -> 200 with execution.status='failed', not a 500")
        print(f"[OK] last_execution recorded on the workflow; status field left alone")


def test_execution_does_not_disturb_pause_state():
    print("\n" + "=" * 70)
    print("Phase E Test 5: Execution never disturbs the pause/resume lifecycle")
    print("=" * 70)

    from main import app
    from fastapi.testclient import TestClient
    from app.services.tenancy import ADMIN_KEY

    with TestClient(app) as client:
        resp = client.post(
            "/tenants", params={"name": "Pause Exec Tenant", "tenant_id": "pause-exec-tenant"},
            headers={"X-Admin-Key": ADMIN_KEY},
        )
        assert resp.status_code == 200, resp.text
        headers = {"X-API-Key": resp.json()["api_key"]}

        wf_id = "pause-exec-wf"
        resp = client.post("/workflows/create", params={"workflow_id": wf_id}, json={"steps": []}, headers=headers)
        assert resp.status_code == 200, resp.text

        now = datetime.utcnow()
        for hour in range(24):
            client.post(
                "/optimization/metrics/record",
                params={"workflow_id": wf_id, "metric_type": "views", "value": max(100, 1000 - hour * 40), "engine": "marketing"},
                headers=headers,
            )
            client.post(
                "/optimization/metrics/record",
                params={"workflow_id": wf_id, "metric_type": "conversions", "value": max(0, 30 - hour), "engine": "analytics"},
                headers=headers,
            )

        resp = client.post(f"/optimization/optimize/{wf_id}/apply", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["decision"]["action"] == "pause"

        resp = client.get(f"/workflows/{wf_id}", headers=headers)
        assert resp.json()["status"] == "paused"

        resp = client.post(f"/workflows/{wf_id}/execute", headers=headers)
        assert resp.status_code == 200, resp.text

        resp = client.get(f"/workflows/{wf_id}", headers=headers)
        workflow = resp.json()
        assert workflow["status"] == "paused", "Execution must not disturb the pause/resume lifecycle status"
        assert "last_execution" in workflow

        print(f"\n[OK] Workflow paused via PAUSE decision (status='paused')")
        print(f"[OK] Executing it afterward leaves status='paused' - the two lifecycles stay independent")


def main():
    print("\n" + "=" * 70)
    print("OS42 Phase E: Workflow Execution")
    print("=" * 70)

    try:
        asyncio.run(test_multi_step_workflow_with_parameter_resolution())
        asyncio.run(test_step_failure_with_continue_does_not_abort_workflow())
        asyncio.run(test_step_failure_with_stop_aborts_workflow())
        test_http_execute_lifecycle()
        test_execution_does_not_disturb_pause_state()

        print("\n" + "=" * 70)
        print("[OK] PHASE E TEST COMPLETE - WorkflowExecutor is finally wired into the live API")
        print("=" * 70 + "\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Phase E test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
