#!/usr/bin/env python3
"""
Phase C test: Multi-Tenancy (service layer)

Proves that two tenants using the *same* workflow_id never see each
other's metrics, analysis, or optimization decisions.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add app to path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.services.metrics_aggregator import MetricsAggregator, MetricPoint, MetricType
from app.services.optimization_engine import OptimizationEngine, OptimizationAction
from app.services.tenancy import TenantRegistry


TENANT_A = "tenant-a"
TENANT_B = "tenant-b"
SHARED_WORKFLOW_ID = "pillar-001"  # deliberately identical across tenants


def test_tenant_registry():
    """Test Phase C.1: Tenant registry and API-key resolution"""
    print("\n" + "=" * 70)
    print("Phase C Test 1: Tenant Registry")
    print("=" * 70)

    registry = TenantRegistry()
    acme = registry.register(name="Acme Inc", tenant_id=TENANT_A)
    globex = registry.register(name="Globex Corp", tenant_id=TENANT_B)

    assert acme.api_key != globex.api_key, "Tenants must get distinct API keys"
    assert registry.get_by_api_key(acme.api_key).tenant_id == TENANT_A
    assert registry.get_by_api_key(globex.api_key).tenant_id == TENANT_B
    assert registry.get_by_api_key("not-a-real-key") is None

    try:
        registry.register(name="Acme Inc Duplicate", tenant_id=TENANT_A)
        assert False, "Registering a duplicate tenant_id should raise"
    except ValueError:
        pass

    print(f"\n[OK] Registered tenants with distinct API keys")
    print(f"  - {acme.tenant_id}: {acme.api_key[:12]}...")
    print(f"  - {globex.tenant_id}: {globex.api_key[:12]}...")
    print("[OK] API-key lookup resolves the correct tenant")
    print("[OK] Duplicate tenant_id registration rejected")

    return acme, globex


def test_metrics_isolation():
    """Test Phase C.2: Metrics isolation across tenants sharing a workflow_id"""
    print("\n" + "=" * 70)
    print("Phase C Test 2: Metrics Isolation")
    print("=" * 70)

    aggregator = MetricsAggregator()
    now = datetime.utcnow()

    # Tenant A: strong performer on "pillar-001"
    for hour in range(24):
        ts = now - timedelta(hours=24 - hour)
        aggregator.add_metric(MetricPoint(
            timestamp=ts, metric_type=MetricType.VIEWS, value=1000 + hour * 50,
            engine="marketing", workflow_id=SHARED_WORKFLOW_ID, tenant_id=TENANT_A
        ))
        aggregator.add_metric(MetricPoint(
            timestamp=ts, metric_type=MetricType.CONVERSIONS, value=60 + hour * 2,
            engine="analytics", workflow_id=SHARED_WORKFLOW_ID, tenant_id=TENANT_A
        ))

    # Tenant B: declining performer on the SAME workflow_id
    for hour in range(24):
        ts = now - timedelta(hours=24 - hour)
        aggregator.add_metric(MetricPoint(
            timestamp=ts, metric_type=MetricType.VIEWS, value=max(100, 1000 - hour * 40),
            engine="marketing", workflow_id=SHARED_WORKFLOW_ID, tenant_id=TENANT_B
        ))
        aggregator.add_metric(MetricPoint(
            timestamp=ts, metric_type=MetricType.CONVERSIONS, value=max(0, 30 - hour),
            engine="analytics", workflow_id=SHARED_WORKFLOW_ID, tenant_id=TENANT_B
        ))

    a_metrics = aggregator.get_metrics(SHARED_WORKFLOW_ID, tenant_id=TENANT_A)
    b_metrics = aggregator.get_metrics(SHARED_WORKFLOW_ID, tenant_id=TENANT_B)
    other_metrics = aggregator.get_metrics(SHARED_WORKFLOW_ID, tenant_id="tenant-with-no-data")

    assert len(a_metrics) == 48, f"Expected 48 points for tenant A, got {len(a_metrics)}"
    assert len(b_metrics) == 48, f"Expected 48 points for tenant B, got {len(b_metrics)}"
    assert all(m.tenant_id == TENANT_A for m in a_metrics), "Tenant A leaked another tenant's metric"
    assert all(m.tenant_id == TENANT_B for m in b_metrics), "Tenant B leaked another tenant's metric"
    assert other_metrics == [], "Unknown tenant must see zero metrics"
    assert len(aggregator.metrics) == 96, "Flat audit log should still contain both tenants' points"

    print(f"\n[OK] Tenant A sees {len(a_metrics)} points for '{SHARED_WORKFLOW_ID}' (all tagged tenant A)")
    print(f"[OK] Tenant B sees {len(b_metrics)} points for '{SHARED_WORKFLOW_ID}' (all tagged tenant B)")
    print(f"[OK] Unknown tenant sees 0 points for '{SHARED_WORKFLOW_ID}'")
    print(f"[OK] No cross-tenant leakage despite identical workflow_id")

    return aggregator


def test_analysis_isolation(aggregator):
    """Test Phase C.3: Performance analysis differs per tenant for the same workflow_id"""
    print("\n" + "=" * 70)
    print("Phase C Test 3: Performance Analysis Isolation")
    print("=" * 70)

    analysis_a = aggregator.analyze_performance(SHARED_WORKFLOW_ID, 24, tenant_id=TENANT_A)
    analysis_b = aggregator.analyze_performance(SHARED_WORKFLOW_ID, 24, tenant_id=TENANT_B)

    assert analysis_a.tenant_id == TENANT_A
    assert analysis_b.tenant_id == TENANT_B
    assert analysis_a.conversion_rate != analysis_b.conversion_rate, \
        "Tenants with different underlying data must not get identical analysis"

    print(f"\nTenant A ({SHARED_WORKFLOW_ID}): conversion_rate={analysis_a.conversion_rate:.2%}")
    print(f"Tenant B ({SHARED_WORKFLOW_ID}): conversion_rate={analysis_b.conversion_rate:.2%}")
    print("\n[OK] Same workflow_id, different tenants -> independent analysis")

    return analysis_a, analysis_b


def test_optimization_isolation(aggregator):
    """Test Phase C.4: Optimization decisions and history are per-tenant"""
    print("\n" + "=" * 70)
    print("Phase C Test 4: Optimization Decision Isolation")
    print("=" * 70)

    engine = OptimizationEngine(aggregator)

    decision_a = engine.analyze_and_optimize(SHARED_WORKFLOW_ID, 24, tenant_id=TENANT_A)
    decision_b = engine.analyze_and_optimize(SHARED_WORKFLOW_ID, 24, tenant_id=TENANT_B)

    print(f"\nTenant A decision: {decision_a.action} (tenant_id={decision_a.tenant_id})")
    print(f"Tenant B decision: {decision_b.action} (tenant_id={decision_b.tenant_id})")

    assert decision_a.tenant_id == TENANT_A
    assert decision_b.tenant_id == TENANT_B
    assert decision_a.action == OptimizationAction.SCALE_BUDGET, "Tenant A (high conversion) should scale"
    assert decision_b.action == OptimizationAction.PAUSE, "Tenant B (declining) should pause"

    history_a = engine.get_execution_history(SHARED_WORKFLOW_ID, tenant_id=TENANT_A)
    history_b = engine.get_execution_history(SHARED_WORKFLOW_ID, tenant_id=TENANT_B)

    assert len(history_a) == 1 and history_a[0] is decision_a
    assert len(history_b) == 1 and history_b[0] is decision_b

    assert engine.should_run_workflow(SHARED_WORKFLOW_ID, tenant_id=TENANT_A) is True
    assert engine.should_run_workflow(SHARED_WORKFLOW_ID, tenant_id=TENANT_B) is False

    # A tenant with no history at all for this workflow_id should default to "run"
    assert engine.should_run_workflow(SHARED_WORKFLOW_ID, tenant_id="tenant-with-no-data") is True

    print("\n[OK] Same workflow_id resolves to different decisions per tenant")
    print("[OK] Execution history isolated per tenant (1 entry each, no cross-contamination)")
    print("[OK] should_run_workflow respects per-tenant pause state")

    return engine


def test_sequencing_isolation(engine):
    """Test Phase C.5: Workflow sequencing only ranks the caller's own workflows"""
    print("\n" + "=" * 70)
    print("Phase C Test 5: Workflow Sequencing Isolation")
    print("=" * 70)

    # Tenant A also has a second workflow with no history yet
    workflows_a = [{"id": SHARED_WORKFLOW_ID}, {"id": "growth-001"}]
    sequence_a = engine.recommend_workflow_sequence(workflows_a, tenant_id=TENANT_A)

    workflows_b = [{"id": SHARED_WORKFLOW_ID}]
    sequence_b = engine.recommend_workflow_sequence(workflows_b, tenant_id=TENANT_B)

    assert SHARED_WORKFLOW_ID in sequence_a
    assert SHARED_WORKFLOW_ID in sequence_b
    assert "growth-001" not in sequence_b, "Tenant B never registered growth-001"

    print(f"\nTenant A sequence: {sequence_a}")
    print(f"Tenant B sequence: {sequence_b}")
    print("\n[OK] Sequencing only considers the requesting tenant's own workflows")


def main():
    print("\n" + "=" * 70)
    print("OS42 Phase C: Multi-Tenancy")
    print("=" * 70)

    try:
        test_tenant_registry()
        aggregator = test_metrics_isolation()
        test_analysis_isolation(aggregator)
        engine = test_optimization_isolation(aggregator)
        test_sequencing_isolation(engine)

        print("\n" + "=" * 70)
        print("[OK] PHASE C TEST COMPLETE - Multi-Tenant Isolation Works")
        print("=" * 70 + "\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Phase C test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
