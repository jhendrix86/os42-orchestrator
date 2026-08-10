#!/usr/bin/env python3
"""
Phase F test: Live integration against a real (mock) engine

Every prior test has proven the orchestrator degrades gracefully when
engines are unreachable - which has been true 100% of the time so far,
since none of the 11 sibling engine repos actually implement anything.
This test proves the other half: when something real IS listening,
workflows actually execute successfully and decisions actually apply
successfully - over a genuine network connection to a genuinely separate
OS process (mock_engines.py, started as a real subprocess bound to a
real port), not an in-process ASGI fake like every other test in this
repo uses.
"""

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).parent
MOCK_PORT = 9123  # unlikely to collide with anything else in this workspace
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}"

# Point every engine at the mock, before importing anything from app.* -
# app/config.py reads these env vars at import time.
for _var in [
    "CONTENT_ENGINE_URL", "MARKETING_ENGINE_URL", "ANALYTICS_ENGINE_URL",
    "MONITORING_ENGINE_URL", "NOTIFICATION_ENGINE_URL", "SALES_ENGINE_URL",
    "REVENUE_ENGINE_URL", "INTEGRATION_ENGINE_URL", "PRICING_ENGINE_URL",
    "SUPPORT_ENGINE_URL", "GOVERNANCE_ENGINE_URL",
]:
    os.environ[_var] = MOCK_URL

sys.path.insert(0, str(REPO_ROOT / "app"))


def wait_for_health(url: str, timeout: float = 10.0):
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1) as resp:
                if resp.status == 200:
                    return
        except Exception as e:
            last_error = e
            time.sleep(0.1)
    raise RuntimeError(f"mock_engines.py never became healthy: {last_error}")


def start_mock_engines() -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "mock_engines.py")],
        cwd=str(REPO_ROOT),
        env={**os.environ, "MOCK_ENGINES_PORT": str(MOCK_PORT)},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        wait_for_health(MOCK_URL)
    except Exception:
        proc.terminate()
        out, _ = proc.communicate(timeout=5)
        print(out)
        raise
    return proc


def test_workflow_executes_successfully_against_a_real_engine(client, headers):
    print("\n" + "=" * 70)
    print("Phase F Test 1: Workflow executes successfully against a real engine")
    print("=" * 70)

    wf_id = "live-pillar-001"
    definition = {
        "steps": [
            {"id": "create_pillar", "engine": "content", "action": "create",
             "params": {"title": "Live Test", "topic": "integration"}, "on_error": "stop"},
            {"id": "repurpose", "engine": "content", "action": "repurpose",
             "params": {"content_id": "$steps.create_pillar.id"}, "on_error": "stop"},
            {"id": "distribute", "engine": "marketing", "action": "distribute",
             "params": {"content_id": "$steps.create_pillar.id"}, "on_error": "stop"},
        ]
    }
    resp = client.post("/workflows/create", params={"workflow_id": wf_id}, json=definition, headers=headers)
    assert resp.status_code == 200, resp.text

    resp = client.post(f"/workflows/{wf_id}/execute", headers=headers)
    assert resp.status_code == 200, resp.text
    execution = resp.json()["execution"]

    assert execution["status"] == "completed", execution
    assert execution["steps"] == 3
    assert execution["results"]["create_pillar"]["status"] == "ok"
    assert execution["results"]["create_pillar"]["id"].startswith("mock-")
    assert execution["results"]["repurpose"]["received"]["content_id"] == execution["results"]["create_pillar"]["id"], \
        "Step 2's $steps.create_pillar.id must have resolved to step 1's real returned id"
    assert execution["results"]["distribute"]["status"] == "ok"

    print(f"\n[OK] 3-step workflow completed for real against a genuinely separate process")
    print(f"[OK] $steps.create_pillar.id correctly threaded through step 2's real HTTP call")


def test_decision_applies_successfully_against_a_real_engine(client, headers):
    print("\n" + "=" * 70)
    print("Phase F Test 2: SCALE_BUDGET decision applies successfully against a real engine")
    print("=" * 70)

    wf_id = "live-scale-001"
    for hour in range(24):
        client.post(
            "/optimization/metrics/record",
            params={"workflow_id": wf_id, "metric_type": "views", "value": 1000 + hour * 50, "engine": "marketing"},
            headers=headers,
        )
        client.post(
            "/optimization/metrics/record",
            params={"workflow_id": wf_id, "metric_type": "conversions", "value": 60 + hour * 2, "engine": "analytics"},
            headers=headers,
        )

    resp = client.post(f"/optimization/optimize/{wf_id}/apply", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"]["action"] == "scale_budget"
    assert body["execution"]["status"] == "applied", body["execution"]
    assert body["execution"]["engine_called"] == "marketing"

    print(f"\n[OK] SCALE_BUDGET -> execution.status='applied' (not 'failed', for the first time in this repo)")


def main():
    print("\n" + "=" * 70)
    print("OS42 Phase F: Live Integration (real mock engine, real subprocess)")
    print("=" * 70)

    mock_proc = start_mock_engines()
    print(f"[mock_engines.py healthy on {MOCK_URL}]")

    try:
        from main import app
        from fastapi.testclient import TestClient
        from app.services.tenancy import ADMIN_KEY

        with TestClient(app) as client:
            resp = client.post(
                "/tenants", params={"name": "Live Tenant", "tenant_id": "live-tenant"},
                headers={"X-Admin-Key": ADMIN_KEY},
            )
            assert resp.status_code == 200, resp.text
            headers = {"X-API-Key": resp.json()["api_key"]}

            test_workflow_executes_successfully_against_a_real_engine(client, headers)
            test_decision_applies_successfully_against_a_real_engine(client, headers)

        print("\n" + "=" * 70)
        print("[OK] PHASE F TEST COMPLETE - the orchestrator works end-to-end against a real engine")
        print("=" * 70 + "\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Phase F test error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        mock_proc.terminate()
        try:
            mock_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            mock_proc.kill()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
