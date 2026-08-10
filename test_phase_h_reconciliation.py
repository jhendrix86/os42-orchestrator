#!/usr/bin/env python3
"""
Phase H test: Reconciliation with the real engine fleet

Proves the concrete fixes from the 2026-08-10 reconciliation pass actually
work (see CLAUDE.md at the repo root for the full story of what was wrong
and why): action-path templating for real ID-scoped REST endpoints, the
corrected engine ports, optional Unkey auth headers, and - the real test -
create_content_pillar_workflow() (verified against real content-engine
router code, never exercised by any test before this) actually executing
successfully end-to-end against mock_engines.py, the same real subprocess
pattern Phase F introduced.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "app"))

import asyncio
import httpx
from fastapi import FastAPI, Request

from app.services.workflow_executor import WorkflowExecutor


# ---------------------------------------------------------------------------
# Part 1: action-path templating (service layer)
# ---------------------------------------------------------------------------

def build_fake_content_engine():
    """A fake engine with a REAL FastAPI path parameter - proves the
    resolved action string is a genuine URL path, not just a string match"""
    app = FastAPI()
    received = []

    @app.post("/content/generate")
    async def generate(request: Request):
        body = await request.json()
        received.append(("generate", None, body))
        return {"id": "abc-123", "title": body.get("title")}

    @app.post("/content/{content_id}/repurpose")
    async def repurpose(content_id: str, request: Request):
        body = await request.json()
        received.append(("repurpose", content_id, body))
        return {"source_content_id": content_id, "derivatives": []}

    return app, received


async def test_action_path_templating():
    print("\n" + "=" * 70)
    print("Phase H Test 1: $steps.x.y resolves inside the action path itself")
    print("=" * 70)

    fake_app, received = build_fake_content_engine()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=fake_app), base_url="http://fake")
    executor = WorkflowExecutor(engine_urls={"content": "http://fake"}, client=client)
    await executor.connect()

    definition = {
        "steps": [
            {"id": "create_pillar", "engine": "content", "action": "content/generate",
             "params": {"title": "Real Test"}, "on_error": "stop"},
            {"id": "repurpose", "engine": "content", "action": "content/$steps.create_pillar.id/repurpose",
             "params": {"target_types": ["social_media"]}, "on_error": "stop"},
        ]
    }
    result = await executor.execute_workflow("wf-templating", definition)
    await executor.disconnect()

    assert result["status"] == "completed", result
    assert received[1][1] == "abc-123", \
        f"Expected the real FastAPI path param to be step 1's real id, got {received[1][1]}"
    assert result["results"]["repurpose"]["source_content_id"] == "abc-123"

    print(f"\n[OK] action='content/$steps.create_pillar.id/repurpose' resolved to")
    print(f"     a real URL the fake engine's {{content_id}} path parameter actually parsed")


# ---------------------------------------------------------------------------
# Part 2: auth headers
# ---------------------------------------------------------------------------

def test_engine_auth_headers():
    print("\n" + "=" * 70)
    print("Phase H Test 2: engine_auth_headers() - opt-in Unkey Bearer token")
    print("=" * 70)

    import app.config as config
    original = config.UNKEY_API_KEY
    try:
        config.UNKEY_API_KEY = None
        assert config.engine_auth_headers() == {}, "Unconfigured must send no auth header"

        config.UNKEY_API_KEY = "test-key-123"
        assert config.engine_auth_headers() == {"Authorization": "Bearer test-key-123"}
    finally:
        config.UNKEY_API_KEY = original

    print(f"\n[OK] No UNKEY_API_KEY -> no Authorization header sent")
    print(f"[OK] UNKEY_API_KEY set -> 'Authorization: Bearer <key>' sent")


# ---------------------------------------------------------------------------
# Part 3: ports match the verified real map
# ---------------------------------------------------------------------------

def test_ports_match_verified_map():
    print("\n" + "=" * 70)
    print("Phase H Test 3: ENGINE_URLS ports match HANDOFF.md's real port map")
    print("=" * 70)

    from app.config import ENGINE_URLS

    # Source of truth: C:\Users\Jonat\CascadeProjects\HANDOFF.md's port map,
    # cross-verified against each engine's real main.py by the 2026-08-10
    # reconciliation's research agent.
    expected_ports = {
        "content": "8040", "marketing": "8039", "analytics": "8042",
        "monitoring": "8043", "notification": "8037", "sales": "8041",
        "revenue": "8036", "integration": "8044", "support": "8038",
        "governance": "8033",
    }

    for engine, port in expected_ports.items():
        assert engine in ENGINE_URLS, f"Missing engine: {engine}"
        assert ENGINE_URLS[engine].endswith(port), \
            f"{engine}: expected port {port}, got {ENGINE_URLS[engine]}"

    assert "pricing" not in ENGINE_URLS, \
        "pricing-intelligence-system isn't an HTTP service - must not be an HTTP peer"

    print(f"\n[OK] All {len(expected_ports)} ports match the verified real map")
    print(f"[OK] 'pricing' correctly absent (not an HTTP service)")


# ---------------------------------------------------------------------------
# Part 4: the real content pillar workflow, executed for the first time ever
# ---------------------------------------------------------------------------

def test_real_content_pillar_workflow_executes_against_mock_engine():
    print("\n" + "=" * 70)
    print("Phase H Test 4: create_content_pillar_workflow() executes for real")
    print("=" * 70)
    print("(never imported/called anywhere else in this repo before this test)")

    import os
    import subprocess
    import time
    import urllib.request

    REPO_ROOT = Path(__file__).parent
    MOCK_PORT = 9124
    MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}"

    # app.config.ENGINE_URLS was already built (from env vars, at import
    # time) by this file's own top-level `from app.services.workflow_executor
    # import WorkflowExecutor` in Test 1 - setting os.environ this late
    # wouldn't do anything. Mutate the already-loaded dict directly instead;
    # main.py's WorkflowExecutor holds a reference to this same dict object,
    # not a copy, so this reaches it.
    from app.config import ENGINE_URLS
    original_content_url = ENGINE_URLS["content"]
    ENGINE_URLS["content"] = MOCK_URL

    def wait_for_health(url, timeout=10.0):
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

    mock_proc = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "mock_engines.py")],
        cwd=str(REPO_ROOT), env={**os.environ, "MOCK_ENGINES_PORT": str(MOCK_PORT)},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        wait_for_health(MOCK_URL)

        from main import app
        from fastapi.testclient import TestClient
        from app.services.tenancy import ADMIN_KEY
        from app.models.workflows import create_content_pillar_workflow

        workflow = create_content_pillar_workflow(title="Reconciliation Test", topic="testing")
        definition = workflow.to_dict()

        with TestClient(app) as client:
            resp = client.post(
                "/tenants", params={"name": "Reconciliation Tenant", "tenant_id": "reconciliation-tenant"},
                headers={"X-Admin-Key": ADMIN_KEY},
            )
            assert resp.status_code == 200, resp.text
            headers = {"X-API-Key": resp.json()["api_key"]}

            resp = client.post(
                "/workflows/create", params={"workflow_id": definition["workflow_id"]},
                json=definition, headers=headers,
            )
            assert resp.status_code == 200, resp.text

            resp = client.post(f"/workflows/{definition['workflow_id']}/execute", headers=headers)
            assert resp.status_code == 200, resp.text
            execution = resp.json()["execution"]

            assert execution["status"] == "completed", execution
            assert execution["steps"] == 5
            for step_id in ["create_pillar", "repurpose_content", "record_distribution",
                             "execute_distribution", "track"]:
                assert step_id in execution["results"], f"Missing step result: {step_id}"
                assert execution["results"][step_id].get("status") != "failed", \
                    f"Step {step_id} failed: {execution['results'][step_id]}"

        print(f"\n[OK] All 5 real, verified steps completed successfully against a real engine")
        print(f"[OK] This is the first time create_content_pillar_workflow() has ever been executed")

    finally:
        ENGINE_URLS["content"] = original_content_url
        mock_proc.terminate()
        try:
            mock_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            mock_proc.kill()


def main():
    print("\n" + "=" * 70)
    print("OS42 Phase H: Reconciliation with the Real Engine Fleet")
    print("=" * 70)

    try:
        asyncio.run(test_action_path_templating())
        test_engine_auth_headers()
        test_ports_match_verified_map()
        test_real_content_pillar_workflow_executes_against_mock_engine()

        print("\n" + "=" * 70)
        print("[OK] PHASE H TEST COMPLETE - Reconciliation fixes verified")
        print("=" * 70 + "\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Phase H test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
