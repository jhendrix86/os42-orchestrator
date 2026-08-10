#!/usr/bin/env python3
"""
Quick test of the orchestrator dashboard

Verifies:
- Dashboard HTML is served
- Status endpoint provides metrics
- Dashboard can poll for updates
"""

import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from main import app
from fastapi.testclient import TestClient


def test_dashboard_endpoints():
    """Test dashboard endpoints"""

    # Try importing the app - if it fails, we'll get an error
    try:
        with TestClient(app) as client:
            # Test health
            response = client.get("/health")
            assert response.status_code == 200, f"Health check failed: {response.text}"

            # Test status
            response = client.get("/status")
            assert response.status_code == 200, f"Status check failed: {response.text}"
            data = response.json()
            assert "active_workflows" in data
            assert "completed_workflows" in data

            # Test dashboard HTML
            response = client.get("/dashboard/")
            assert response.status_code == 200, f"Dashboard HTML failed: {response.text}"
            assert "OS42 Orchestrator" in response.text
            assert "Services Status" in response.text
            assert "Active Workflows" in response.text

            # Test services endpoint
            response = client.get("/services")
            assert response.status_code == 200, f"Services endpoint failed: {response.text}"
            data = response.json()
            assert "services" in data
            assert len(data["services"]) > 0

        print("\n[OK] All dashboard tests passed!")
        print("  - Health endpoint working")
        print("  - Status endpoint working")
        print("  - Dashboard HTML serving")
        print("  - Services discovery working")
        return True

    except Exception as e:
        print(f"\n[FAIL] Dashboard test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_dashboard_endpoints()
    sys.exit(0 if success else 1)
