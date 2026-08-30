#!/usr/bin/env python3
"""
Phase J test: extend Phase H/I's reconciliation pattern to the 5 engines
Stage 4's fleet-wide rollout made genuinely real (per ../HANDOFF.md's
2026-08-12/15 "6 remaining mock engines made real" entry) - notification,
integration, sales, customer-support, analytics. This is Step 9 of the
2026-08-28 roadmap split (../OS42_ROADMAP.md), assigned to HP-14.

Also revisited (per Step 9's second half): DecisionExecutor.ACTION_ENGINE_MAP's
5 unbacked actions (scale_budget, adjust_frequency, change_channel,
adjust_timing, change_format) against current marketing-automation-engine
and content-engine router code. Still nothing real to call - see CLAUDE.md's
2026-08-30 addendum for the one near-miss found (content/{id}/repurpose is
real but doesn't fit the executor's flat POST-only calling contract) and why
it wasn't force-mapped.

Builds four *new* templates around endpoints that are real today on the
five target engines - see workflows.py's docstrings on
create_support_escalation_workflow / create_integration_sync_workflow /
create_analytics_report_workflow / create_lead_conversion_workflow for
exactly which router code each step was verified against.
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


def _run_workflow_against_mock(engine_keys, mock_port: int, workflow, expected_steps):
    """
    Shared harness (Phase F/H/I's real-subprocess pattern, generalized to
    redirect more than one ENGINE_URLS entry at once - this phase's first
    workflow spans two engines in a single execution).
    """
    from app.config import ENGINE_URLS

    mock_url = f"http://127.0.0.1:{mock_port}"
    originals = {k: ENGINE_URLS[k] for k in engine_keys}
    for k in engine_keys:
        ENGINE_URLS[k] = mock_url

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
                "/tenants", params={"name": "Phase J Tenant", "tenant_id": f"phase-j-{'-'.join(engine_keys)}"},
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
        for k, v in originals.items():
            ENGINE_URLS[k] = v
        mock_proc.terminate()
        try:
            mock_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            mock_proc.kill()


def test_support_escalation_workflow_executes_against_mock_engine():
    print("\n" + "=" * 70)
    print("Phase J Test 1: create_support_escalation_workflow() executes for real")
    print("=" * 70)
    print("(customer-support-engine: tickets/create -> tickets/{id}/escalate,")
    print(" notification-engine: notifications/send - never exercised before this)")

    from app.models.workflows import create_support_escalation_workflow

    workflow = create_support_escalation_workflow(
        customer_name="Test Customer",
        customer_email="customer@example.com",
        subject="Production outage",
        message="API returning 500s for all requests",
        notify_recipient="oncall@example.com",
    )

    execution = _run_workflow_against_mock(
        engine_keys=["support", "notification"], mock_port=9226, workflow=workflow,
        expected_steps=["create_ticket", "escalate_ticket", "notify_oncall"],
    )

    print(f"\n[OK] All 3 real, verified support+notification steps completed")
    print(f"[OK] execution: {execution['status']}, {execution['steps']} steps")


def test_integration_sync_workflow_executes_against_mock_engine():
    print("\n" + "=" * 70)
    print("Phase J Test 2: create_integration_sync_workflow() executes for real")
    print("=" * 70)
    print("(integration-engine: integrations/create -> integrations/{id}/sync -")
    print(" never exercised by any test before this)")

    from app.models.workflows import create_integration_sync_workflow

    workflow = create_integration_sync_workflow(
        name="Test Webhook Integration",
        provider="generic",
        sync_url="https://example.com/sync-endpoint",
    )

    execution = _run_workflow_against_mock(
        engine_keys=["integration"], mock_port=9227, workflow=workflow,
        expected_steps=["create_integration", "trigger_sync"],
    )

    print(f"\n[OK] Both real, verified integration-engine steps completed")
    print(f"[OK] execution: {execution['status']}, {execution['steps']} steps")


def test_analytics_report_workflow_executes_against_mock_engine():
    print("\n" + "=" * 70)
    print("Phase J Test 3: create_analytics_report_workflow() executes for real")
    print("=" * 70)
    print("(analytics-engine: reports/ -> reports/{id}/generate - never")
    print(" exercised by any test before this)")

    from app.models.workflows import create_analytics_report_workflow

    workflow = create_analytics_report_workflow(
        report_name="Weekly Engagement Summary",
        metric_names=["views", "conversions"],
        period_days=7,
    )

    execution = _run_workflow_against_mock(
        engine_keys=["analytics"], mock_port=9228, workflow=workflow,
        expected_steps=["create_report", "generate_report"],
    )

    print(f"\n[OK] Both real, verified analytics-engine steps completed")
    print(f"[OK] execution: {execution['status']}, {execution['steps']} steps")


def test_lead_conversion_workflow_executes_against_mock_engine():
    print("\n" + "=" * 70)
    print("Phase J Test 4: create_lead_conversion_workflow() executes for real")
    print("=" * 70)
    print("(sales-engine: leads/create -> leads/{id}/convert - never")
    print(" exercised by any test before this)")

    from app.models.workflows import create_lead_conversion_workflow

    workflow = create_lead_conversion_workflow(
        lead_name="Test Prospect",
        lead_email="prospect@example.com",
        estimated_value=5000,
    )

    execution = _run_workflow_against_mock(
        engine_keys=["sales"], mock_port=9229, workflow=workflow,
        expected_steps=["create_lead", "convert_lead"],
    )

    print(f"\n[OK] Both real, verified sales-engine steps completed")
    print(f"[OK] execution: {execution['status']}, {execution['steps']} steps")


def main():
    print("\n" + "=" * 70)
    print("OS42 Phase J: Extending reconciliation to the 5 Stage-4-real engines")
    print("=" * 70)

    try:
        test_support_escalation_workflow_executes_against_mock_engine()
        test_integration_sync_workflow_executes_against_mock_engine()
        test_analytics_report_workflow_executes_against_mock_engine()
        test_lead_conversion_workflow_executes_against_mock_engine()

        print("\n" + "=" * 70)
        print("[OK] PHASE J TEST COMPLETE - four new workflows verified")
        print("=" * 70 + "\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Phase J test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
