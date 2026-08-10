#!/usr/bin/env python3
"""
Phase D test (part 4): Goal-based workflow sequencing

Proves a tenant's stated goal actually changes how
recommend_workflow_sequence() prioritizes that tenant's workflows - not
just that the field round-trips through the API. Two decisions are
constructed with equal base scores (confidence x impact) so that only the
goal's action-bonus weighting can move one ahead of the other; if the
sequencing were goal-blind, the order would never flip.
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.services.metrics_aggregator import MetricsAggregator, OptimizationAction
from app.services.optimization_engine import OptimizationDecision, OptimizationEngine, VALID_GOALS


def make_decision(workflow_id: str, tenant_id: str, action: OptimizationAction) -> OptimizationDecision:
    """confidence=0.5, estimated_impact=0 for every decision - equal base
    scores, so only the goal's action bonus can separate them"""
    return OptimizationDecision(
        workflow_id=workflow_id, tenant_id=tenant_id, timestamp=datetime.utcnow(),
        action=action, reason="test", confidence=0.5, estimated_impact=0.0,
    )


def test_goal_flips_priority_order():
    print("\n" + "=" * 70)
    print("Phase D Goals Test 1: Goal changes sequencing order for identical base scores")
    print("=" * 70)

    engine = OptimizationEngine(MetricsAggregator())
    tenant_id = "goal-tenant"

    engine.restore(make_decision("wf-scale", tenant_id, OptimizationAction.SCALE_BUDGET))
    engine.restore(make_decision("wf-pause", tenant_id, OptimizationAction.PAUSE))

    workflows = [{"id": "wf-scale"}, {"id": "wf-pause"}]

    balanced = engine.recommend_workflow_sequence(workflows, tenant_id=tenant_id, goal="balanced")
    risk_averse = engine.recommend_workflow_sequence(workflows, tenant_id=tenant_id, goal="minimize_risk")

    assert balanced == ["wf-scale", "wf-pause"], balanced
    assert risk_averse == ["wf-pause", "wf-scale"], risk_averse
    assert balanced != risk_averse, "Goal must actually change the order, not just the field"

    print(f"\n[OK] goal='balanced'      -> {balanced} (SCALE_BUDGET favored)")
    print(f"[OK] goal='minimize_risk' -> {risk_averse} (PAUSE favored - order flipped)")


def test_unknown_goal_falls_back_to_balanced():
    print("\n" + "=" * 70)
    print("Phase D Goals Test 2: Unknown goal falls back to balanced, doesn't crash")
    print("=" * 70)

    engine = OptimizationEngine(MetricsAggregator())
    tenant_id = "goal-tenant-2"
    engine.restore(make_decision("wf-scale", tenant_id, OptimizationAction.SCALE_BUDGET))
    engine.restore(make_decision("wf-pause", tenant_id, OptimizationAction.PAUSE))
    workflows = [{"id": "wf-scale"}, {"id": "wf-pause"}]

    balanced = engine.recommend_workflow_sequence(workflows, tenant_id=tenant_id, goal="balanced")
    nonsense = engine.recommend_workflow_sequence(workflows, tenant_id=tenant_id, goal="not-a-real-goal")

    assert nonsense == balanced, "Unrecognized goal must fall back to balanced weights, not raise"
    print(f"\n[OK] Unknown goal string produced the same result as 'balanced': {nonsense}")


def test_http_goal_endpoints():
    print("\n" + "=" * 70)
    print("Phase D Goals Test 3: HTTP goal endpoints - create, view, update, validate")
    print("=" * 70)

    from main import app
    from fastapi.testclient import TestClient
    from app.services.tenancy import ADMIN_KEY

    with TestClient(app) as client:
        # Default goal on creation
        resp = client.post(
            "/tenants", params={"name": "Goals HTTP Tenant", "tenant_id": "goals-http-tenant"},
            headers={"X-Admin-Key": ADMIN_KEY},
        )
        assert resp.status_code == 200, resp.text
        tenant = resp.json()
        assert tenant["goal"] == "balanced"
        headers = {"X-API-Key": tenant["api_key"]}

        resp = client.get("/tenants/me", headers=headers)
        assert resp.json()["goal"] == "balanced"

        # Update it
        resp = client.put("/tenants/me/goal", params={"goal": "maximize_growth"}, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["goal"] == "maximize_growth"

        resp = client.get("/tenants/me", headers=headers)
        assert resp.json()["goal"] == "maximize_growth", "Update must persist across requests"

        # Reject invalid goal
        resp = client.put("/tenants/me/goal", params={"goal": "worldDomination"}, headers=headers)
        assert resp.status_code == 400, resp.text

        # Create with an explicit initial goal
        resp = client.post(
            "/tenants",
            params={"name": "Risk Averse Tenant", "tenant_id": "goals-http-tenant-2", "goal": "minimize_risk"},
            headers={"X-Admin-Key": ADMIN_KEY},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["goal"] == "minimize_risk"

        print(f"\n[OK] New tenants default to goal='balanced'")
        print(f"[OK] PUT /tenants/me/goal updates and persists (visible on next GET)")
        print(f"[OK] Invalid goal -> 400")
        print(f"[OK] POST /tenants accepts an explicit initial goal")


def test_http_recommendations_reflect_goal_change():
    print("\n" + "=" * 70)
    print("Phase D Goals Test 4: /optimization/recommendations reorders when goal changes")
    print("=" * 70)

    from main import app
    from fastapi.testclient import TestClient
    from app.services.tenancy import ADMIN_KEY
    from app.routes.optimization import optimization_engine

    with TestClient(app) as client:
        resp = client.post(
            "/tenants", params={"name": "Recs Goal Tenant", "tenant_id": "recs-goal-tenant"},
            headers={"X-Admin-Key": ADMIN_KEY},
        )
        tenant = resp.json()
        headers = {"X-API-Key": tenant["api_key"]}

        # Seed two decisions with equal base scores directly, same technique
        # as the service-layer test - guarantees the order can actually flip.
        optimization_engine.restore(make_decision("wf-scale", tenant["tenant_id"], OptimizationAction.SCALE_BUDGET))
        optimization_engine.restore(make_decision("wf-pause", tenant["tenant_id"], OptimizationAction.PAUSE))

        resp = client.get(
            "/optimization/recommendations",
            params={"workflow_ids": "wf-scale,wf-pause"}, headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["goal"] == "balanced"
        assert body["recommended_sequence"] == ["wf-scale", "wf-pause"]

        client.put("/tenants/me/goal", params={"goal": "minimize_risk"}, headers=headers)

        resp = client.get(
            "/optimization/recommendations",
            params={"workflow_ids": "wf-scale,wf-pause"}, headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["goal"] == "minimize_risk"
        assert body["recommended_sequence"] == ["wf-pause", "wf-scale"], body

        print(f"\n[OK] goal='balanced' -> sequence favors SCALE_BUDGET first")
        print(f"[OK] After PUT-ing goal='minimize_risk' -> sequence flips to favor PAUSE first")
        print(f"[OK] Response echoes the goal that produced the sequence")


def main():
    print("\n" + "=" * 70)
    print("OS42 Phase D (part 4): Goal-based Workflow Sequencing")
    print("=" * 70)
    print(f"Valid goals: {sorted(VALID_GOALS)}")

    try:
        test_goal_flips_priority_order()
        test_unknown_goal_falls_back_to_balanced()
        test_http_goal_endpoints()
        test_http_recommendations_reflect_goal_change()

        print("\n" + "=" * 70)
        print("[OK] PHASE D GOALS TEST COMPLETE - Tenant goals actually change sequencing")
        print("=" * 70 + "\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Phase D goals test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
