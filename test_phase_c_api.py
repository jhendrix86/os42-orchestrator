#!/usr/bin/env python3
"""
Phase C test: Multi-Tenancy (HTTP layer)

Drives the real FastAPI endpoints with TestClient to prove:
- Missing/invalid API keys are rejected with 401
- Tenant provisioning requires the admin key
- Two tenants calling the HTTP API never see each other's workflows or
  metrics, even when they use identical workflow_ids
"""

import sys
from pathlib import Path

# Add app to path (mirrors test_dashboard.py's import convention)
sys.path.insert(0, str(Path(__file__).parent / "app"))

from main import app
from fastapi.testclient import TestClient
from app.services.tenancy import ADMIN_KEY

SHARED_WORKFLOW_ID = "http-pillar-001"


def test_auth_required(client):
    """Requests without a valid API key are rejected"""
    print("\n" + "=" * 70)
    print("Phase C API Test 1: Authentication Required")
    print("=" * 70)

    resp = client.get("/workflows")
    assert resp.status_code == 401, f"Expected 401 with no key, got {resp.status_code}"

    resp = client.get("/workflows", headers={"X-API-Key": "not-a-real-key"})
    assert resp.status_code == 401, f"Expected 401 with bad key, got {resp.status_code}"

    resp = client.post("/tenants", params={"name": "Should Fail"})
    assert resp.status_code == 401, f"Expected 401 provisioning without admin key, got {resp.status_code}"

    print("\n[OK] Missing API key -> 401")
    print("[OK] Invalid API key -> 401")
    print("[OK] Tenant provisioning without admin key -> 401")


def test_tenant_provisioning(client):
    """Admin can provision tenants; a tenant can look up its own record"""
    print("\n" + "=" * 70)
    print("Phase C API Test 2: Tenant Provisioning")
    print("=" * 70)

    resp = client.post(
        "/tenants",
        params={"name": "HTTP Tenant A", "tenant_id": "http-tenant-a"},
        headers={"X-Admin-Key": ADMIN_KEY},
    )
    assert resp.status_code == 200, resp.text
    tenant_a = resp.json()
    assert "api_key" in tenant_a

    resp = client.post(
        "/tenants",
        params={"name": "HTTP Tenant B", "tenant_id": "http-tenant-b"},
        headers={"X-Admin-Key": ADMIN_KEY},
    )
    assert resp.status_code == 200, resp.text
    tenant_b = resp.json()

    assert tenant_a["api_key"] != tenant_b["api_key"]

    resp = client.get("/tenants/me", headers={"X-API-Key": tenant_a["api_key"]})
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "http-tenant-a"

    print(f"\n[OK] Provisioned {tenant_a['tenant_id']} and {tenant_b['tenant_id']} via admin key")
    print("[OK] /tenants/me resolves the caller's own identity from their API key")

    return tenant_a, tenant_b


def test_workflow_isolation(client, tenant_a, tenant_b):
    """Two tenants creating a workflow with the same ID never see each other's data"""
    print("\n" + "=" * 70)
    print("Phase C API Test 3: Workflow Isolation Over HTTP")
    print("=" * 70)

    headers_a = {"X-API-Key": tenant_a["api_key"]}
    headers_b = {"X-API-Key": tenant_b["api_key"]}

    resp = client.post(
        "/workflows/create",
        params={"workflow_id": SHARED_WORKFLOW_ID},
        json={"steps": [{"engine": "content", "action": "create", "params": {}}]},
        headers=headers_a,
    )
    assert resp.status_code == 200, resp.text

    # Tenant B never created this workflow_id
    resp = client.get(f"/workflows/{SHARED_WORKFLOW_ID}", headers=headers_b)
    assert resp.status_code == 404, "Tenant B should not see tenant A's workflow"

    # Tenant A can see its own workflow
    resp = client.get(f"/workflows/{SHARED_WORKFLOW_ID}", headers=headers_a)
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "http-tenant-a"

    resp = client.get("/workflows", headers=headers_b)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0, "Tenant B's workflow list should be empty"

    resp = client.get("/workflows", headers=headers_a)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    print(f"\n[OK] Tenant A created '{SHARED_WORKFLOW_ID}'; tenant B gets 404 for the same ID")
    print("[OK] GET /workflows only ever returns the caller's own workflows")


def test_metrics_isolation_http(client, tenant_a, tenant_b):
    """Metrics recorded by one tenant are invisible to another, even for the same workflow_id"""
    print("\n" + "=" * 70)
    print("Phase C API Test 4: Metrics Isolation Over HTTP")
    print("=" * 70)

    headers_a = {"X-API-Key": tenant_a["api_key"]}
    headers_b = {"X-API-Key": tenant_b["api_key"]}

    resp = client.post(
        "/optimization/metrics/record",
        params={"workflow_id": SHARED_WORKFLOW_ID, "metric_type": "views", "value": 500, "engine": "marketing"},
        headers=headers_a,
    )
    assert resp.status_code == 200, resp.text

    resp = client.get(f"/optimization/metrics/{SHARED_WORKFLOW_ID}", headers=headers_a)
    assert resp.json()["metric_count"] == 1

    resp = client.get(f"/optimization/metrics/{SHARED_WORKFLOW_ID}", headers=headers_b)
    assert resp.json()["metric_count"] == 0, "Tenant B must not see tenant A's metric"

    print("\n[OK] Tenant A recorded a metric; tenant B sees 0 metrics for the same workflow_id")


def main():
    print("\n" + "=" * 70)
    print("OS42 Phase C: Multi-Tenancy (HTTP API)")
    print("=" * 70)

    try:
        with TestClient(app) as client:
            test_auth_required(client)
            tenant_a, tenant_b = test_tenant_provisioning(client)
            test_workflow_isolation(client, tenant_a, tenant_b)
            test_metrics_isolation_http(client, tenant_a, tenant_b)

        print("\n" + "=" * 70)
        print("[OK] PHASE C API TEST COMPLETE - HTTP-layer isolation works")
        print("=" * 70 + "\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Phase C API test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
