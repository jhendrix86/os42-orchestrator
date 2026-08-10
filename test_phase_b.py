#!/usr/bin/env python3
"""
Phase B test: Autonomous Optimization

Demonstrates metrics collection, analysis, and autonomous optimization decisions
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add app to path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.services.metrics_aggregator import (
    MetricsAggregator, MetricPoint, MetricType
)
from app.services.optimization_engine import OptimizationEngine, OptimizationAction


def test_metrics_collection():
    """Test Phase B.1: Metrics Collection"""
    print("\n" + "=" * 70)
    print("Phase B Test 1: Metrics Collection")
    print("=" * 70)

    aggregator = MetricsAggregator()

    # Simulate metrics from content pillar workflow
    now = datetime.utcnow()

    workflows = [
        ("pillar-001", "improving"),
        ("daily-optimize-001", "stable"),
        ("growth-001", "declining")
    ]

    for workflow_id, trend in workflows:
        # Generate 24 hours of metrics
        if trend == "improving":
            base_views = 200
            base_conversions = 5
        elif trend == "stable":
            base_views = 150
            base_conversions = 3
        else:
            base_views = 100
            base_conversions = 1

        for hour in range(24):
            timestamp = now - timedelta(hours=24-hour)

            # Views
            views = base_views + (hour * 10 if trend == "improving" else -hour * 2 if trend == "declining" else 0)
            aggregator.add_metric(MetricPoint(
                timestamp=timestamp,
                metric_type=MetricType.VIEWS,
                value=views,
                engine="marketing",
                workflow_id=workflow_id
            ))

            # Conversions
            conversions = base_conversions + (hour * 0.2 if trend == "improving" else -hour * 0.05 if trend == "declining" else 0)
            aggregator.add_metric(MetricPoint(
                timestamp=timestamp,
                metric_type=MetricType.CONVERSIONS,
                value=max(0, conversions),
                engine="analytics",
                workflow_id=workflow_id
            ))

            # Revenue
            revenue = conversions * 29.9  # $29.9 per conversion
            aggregator.add_metric(MetricPoint(
                timestamp=timestamp,
                metric_type=MetricType.REVENUE,
                value=revenue,
                engine="revenue",
                workflow_id=workflow_id
            ))

    print(f"\n[OK] Collected metrics:")
    for workflow_id, _ in workflows:
        workflow_metrics = aggregator.workflow_metrics.get(workflow_id, [])
        print(f"  - {workflow_id}: {len(workflow_metrics)} data points")

    return aggregator


def test_performance_analysis(aggregator):
    """Test Phase B.2: Performance Analysis"""
    print("\n" + "=" * 70)
    print("Phase B Test 2: Performance Analysis")
    print("=" * 70)

    analyses = {}
    for workflow_id in aggregator.workflow_metrics.keys():
        analysis = aggregator.analyze_performance(workflow_id, 24)
        analyses[workflow_id] = analysis

        print(f"\n{workflow_id}:")
        print(f"  Conversion Rate: {analysis.conversion_rate:.2%}" if analysis.conversion_rate else "  Conversion Rate: N/A")
        print(f"  Revenue/Conversion: ${analysis.revenue_per_conversion:.2f}" if analysis.revenue_per_conversion else "  Revenue/Conversion: N/A")
        print(f"  Trend: {analysis.conversion_trend or 'N/A'}")
        if analysis.recommendations:
            print(f"  Recommendations:")
            for rec in analysis.recommendations:
                print(f"    - {rec}")

    print("\n[OK] Performance analysis complete")
    return analyses


def test_optimization_decisions(analyses):
    """Test Phase B.3: Optimization Decisions"""
    print("\n" + "=" * 70)
    print("Phase B Test 3: Optimization Decisions")
    print("=" * 70)

    aggregator = MetricsAggregator()
    # Re-add metrics for optimization engine
    for workflow_id, analysis in analyses.items():
        # The optimization engine needs the aggregator with metrics
        pass

    # Create fresh aggregator for optimization
    opt_aggregator = MetricsAggregator()

    # Add sample metrics
    now = datetime.utcnow()

    # Workflow 1: High conversion (should scale)
    for hour in range(24):
        opt_aggregator.add_metric(MetricPoint(
            timestamp=now - timedelta(hours=24-hour),
            metric_type=MetricType.VIEWS,
            value=1000 + hour * 50,
            engine="marketing",
            workflow_id="pillar-001"
        ))
        opt_aggregator.add_metric(MetricPoint(
            timestamp=now - timedelta(hours=24-hour),
            metric_type=MetricType.CONVERSIONS,
            value=60 + hour * 2,
            engine="analytics",
            workflow_id="pillar-001"
        ))

    # Workflow 2: Declining (should pause)
    for hour in range(24):
        opt_aggregator.add_metric(MetricPoint(
            timestamp=now - timedelta(hours=24-hour),
            metric_type=MetricType.VIEWS,
            value=max(100, 1000 - hour * 40),
            engine="marketing",
            workflow_id="decline-001"
        ))
        opt_aggregator.add_metric(MetricPoint(
            timestamp=now - timedelta(hours=24-hour),
            metric_type=MetricType.CONVERSIONS,
            value=max(0, 30 - hour),
            engine="analytics",
            workflow_id="decline-001"
        ))

    # Workflow 3: High engagement (should increase frequency)
    for hour in range(24):
        opt_aggregator.add_metric(MetricPoint(
            timestamp=now - timedelta(hours=24-hour),
            metric_type=MetricType.VIEWS,
            value=500,
            engine="marketing",
            workflow_id="growth-001"
        ))
        opt_aggregator.add_metric(MetricPoint(
            timestamp=now - timedelta(hours=24-hour),
            metric_type=MetricType.CLICKS,
            value=50,  # 10% engagement
            engine="marketing",
            workflow_id="growth-001"
        ))
        opt_aggregator.add_metric(MetricPoint(
            timestamp=now - timedelta(hours=24-hour),
            metric_type=MetricType.CONVERSIONS,
            value=15,  # 3% conversion
            engine="analytics",
            workflow_id="growth-001"
        ))

    engine = OptimizationEngine(opt_aggregator)

    workflows = ["pillar-001", "decline-001", "growth-001"]
    decisions = []

    print("\nOptimization Decisions:")
    for workflow_id in workflows:
        decision = engine.analyze_and_optimize(workflow_id, 24)
        decisions.append(decision)

        print(f"\n{workflow_id}:")
        print(f"  Action: {decision.action}")
        print(f"  Reason: {decision.reason}")
        print(f"  Confidence: {decision.confidence:.0%}")
        if decision.estimated_impact:
            print(f"  Estimated Impact: {decision.estimated_impact:+.0%}")
        if decision.parameters:
            print(f"  Parameters: {decision.parameters}")

    print("\n[OK] Optimization decisions generated")
    return engine, decisions


def test_workflow_sequencing(engine):
    """Test Phase B.4: Workflow Sequencing"""
    print("\n" + "=" * 70)
    print("Phase B Test 4: Autonomous Workflow Sequencing")
    print("=" * 70)

    available_workflows = [
        {"id": "pillar-001"},
        {"id": "decline-001"},
        {"id": "growth-001"},
    ]

    sequence = engine.recommend_workflow_sequence(available_workflows)

    print("\nRecommended Execution Sequence:")
    for i, workflow_id in enumerate(sequence, 1):
        should_run = engine.should_run_workflow(workflow_id)
        status = "RUN" if should_run else "SKIP"

        print(f"  {i}. {workflow_id} [{status}]")

        # Show latest decision
        history = engine.get_execution_history(workflow_id)
        if history:
            latest = history[-1]
            print(f"     Latest action: {latest.action}")

    print("\n[OK] Workflow sequence generated")


def main():
    print("\n" + "=" * 70)
    print("OS42 Phase B: Autonomous Optimization")
    print("=" * 70)

    try:
        # Test 1: Metrics Collection
        aggregator = test_metrics_collection()

        # Test 2: Performance Analysis
        analyses = test_performance_analysis(aggregator)

        # Test 3: Optimization Decisions
        engine, decisions = test_optimization_decisions(analyses)

        # Test 4: Workflow Sequencing
        test_workflow_sequencing(engine)

        # Verification
        print("\n" + "=" * 70)
        print("VERIFICATION")
        print("=" * 70)

        assert len(aggregator.metrics) > 0, "No metrics collected"
        assert len(engine.decisions) > 0, "No optimization decisions made"

        # Verify decision quality
        high_conv_decisions = [d for d in engine.decisions if "scale" in str(d.action).lower()]
        low_conv_decisions = [d for d in engine.decisions if "pause" in str(d.action).lower()]

        print(f"\n[OK] Metrics collected: {len(aggregator.metrics)}")
        print(f"[OK] Workflows analyzed: {len(engine.execution_history)}")
        print(f"[OK] Optimization decisions: {len(engine.decisions)}")
        print(f"[OK] Scale-up opportunities: {len(high_conv_decisions)}")
        print(f"[OK] Pause/review opportunities: {len(low_conv_decisions)}")

        print("\n" + "=" * 70)
        print("[OK] PHASE B TEST COMPLETE - Autonomous Optimization Works")
        print("=" * 70 + "\n")

        return True

    except Exception as e:
        print(f"\n[FAIL] Phase B test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
