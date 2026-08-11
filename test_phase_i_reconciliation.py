#!/usr/bin/env python3
"""
Phase I test: extend Phase H's reconciliation pattern to a second and third
engine

Phase H (2026-08-10) verified create_content_pillar_workflow() against real
content-engine router code and proved it executes end-to-end. Its own
follow-up concluded the two *pre-existing* unverified templates
(create_daily_optimization_workflow, create_audience_growth_workflow)
genuinely can't be reconciled - the real endpoints they'd need don't exist
yet anywhere in the fleet (see workflows.py's docstrings on those two).

This phase instead builds two *new* templates around endpoints that ARE
real today, on the two other engines Stage 1/2 already made genuinely
functional (not mock stubs): marketing-automation-engine (leads/campaigns/
email - real SendGrid sending) and revenue-operations-engine (customers/
subscriptions - a real proxy to baselayer's income_engine). See
CLAUDE.md at the repo root and workflows.py's docstrings on
create_lead_nurture_email_workflow / create_customer_subscription_workflow
for exactly which router code each step was verified against.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "app"))

import os
import subprocess
import time
import urllib.request

REPO_ROOT = Path(__file__).parent


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


def _run_workflow_against_mock(engine_key: str, mock_port: int, workflow, expected_steps):
    """
    Shared harness: point one ENGINE_URLS entry at a fresh mock_engines.py
    subprocess (Phase F's real-subprocess pattern), create+execute the given
    workflow through the real HTTP API, and assert every step completed.
    """
    from app.config import ENGINE_URLS

    mock_url = f"http://127.0.0.1:{mock_port}"
    original_url = ENGINE_URLS[engine_key]
    ENGINE_URLS[engine_key] = mock_url

    mock_proc = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "mock_engines.py")],
        cwd=str(REPO_ROOT), env={**os.environ, "MOCK_ENGINES_PORT": str(mock_port)},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        wait_for_health(mock_url)

        from main import app
        from fastapi.testclient import TestClient
        from app.services.tenancy import ADMIN_KEY

        definition = workflow.to_dict()

        with TestClient(app) as client:
            resp = client.post(
                "/tenants", params={"name": "Phase I Tenant", "tenant_id": f"phase-i-{engine_key}"},
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
            assert execution["steps"] == len(expected_steps)
            for step_id in expected_steps:
                assert step_id in execution["results"], f"Missing step result: {step_id}"
                assert execution["results"][step_id].get("status") != "failed", \
                    f"Step {step_id} failed: {execution['results'][step_id]}"

            return execution
    finally:
        ENGINE_URLS[engine_key] = original_url
        mock_proc.terminate()
        try:
            mock_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            mock_proc.kill()


def test_lead_nurture_email_workflow_executes_against_mock_engine():
    print("\n" + "=" * 70)
    print("Phase I Test 1: create_lead_nurture_email_workflow() executes for real")
    print("=" * 70)
    print("(marketing-automation-engine: leads/create -> campaigns/create ->")
    print(" email/create -> email/{id}/send - never exercised by any test before this)")

    from app.models.workflows import create_lead_nurture_email_workflow

    workflow = create_lead_nurture_email_workflow(
        lead_email="prospect@example.com",
        subject="Welcome to the pipeline",
        from_email="hello@example.com",
        lead_name="Test Prospect",
    )

    execution = _run_workflow_against_mock(
        engine_key="marketing", mock_port=9224, workflow=workflow,
        expected_steps=["create_lead", "create_campaign", "create_email_campaign", "send_email_campaign"],
    )

    print(f"\n[OK] All 4 real, verified marketing-automation-engine steps completed")
    print(f"[OK] execution: {execution['status']}, {execution['steps']} steps")


def test_customer_subscription_workflow_executes_against_mock_engine():
    print("\n" + "=" * 70)
    print("Phase I Test 2: create_customer_subscription_workflow() executes for real")
    print("=" * 70)
    print("(revenue-operations-engine: customers/ -> subscriptions/create -")
    print(" never exercised by any test before this)")

    from app.models.workflows import create_customer_subscription_workflow

    workflow = create_customer_subscription_workflow(
        customer_email="customer@example.com",
        plan_id="starter-monthly",
        payment_method_id="pm_test_123",
        customer_name="Test Customer",
    )

    execution = _run_workflow_against_mock(
        engine_key="revenue", mock_port=9225, workflow=workflow,
        expected_steps=["create_customer", "create_subscription"],
    )

    print(f"\n[OK] Both real, verified revenue-operations-engine steps completed")
    print(f"[OK] execution: {execution['status']}, {execution['steps']} steps")


def main():
    print("\n" + "=" * 70)
    print("OS42 Phase I: Extending reconciliation to marketing + revenue engines")
    print("=" * 70)

    try:
        test_lead_nurture_email_workflow_executes_against_mock_engine()
        test_customer_subscription_workflow_executes_against_mock_engine()

        print("\n" + "=" * 70)
        print("[OK] PHASE I TEST COMPLETE - both new workflows verified")
        print("=" * 70 + "\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Phase I test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
