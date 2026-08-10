"""
Optimization routes for OS42 Orchestrator

Provides metrics collection, analysis, and optimization recommendations.
Every endpoint is scoped to the tenant resolved from the X-API-Key header -
callers only ever see their own metrics, decisions, and recommendations.
"""

from fastapi import APIRouter, Depends, Query
from datetime import datetime, timedelta
from typing import List, Optional

from app.models.tenant import Tenant
from app.services.metrics_aggregator import MetricsAggregator, MetricPoint, MetricType
from app.services.optimization_engine import OptimizationEngine
from app.services.tenancy import get_current_tenant

router = APIRouter(
    prefix="/optimization",
    tags=["optimization"],
    dependencies=[Depends(get_current_tenant)],
)

# Global instances (in production these would be in app state / a database).
# Tenant isolation is enforced by tenant_id scoping inside each service, not
# by separate instances per tenant - see MetricsAggregator/OptimizationEngine.
metrics_aggregator = MetricsAggregator()
optimization_engine = OptimizationEngine(metrics_aggregator)


@router.post("/metrics/record")
async def record_metric(
    workflow_id: str, metric_type: MetricType, value: float, engine: str,
    tenant: Tenant = Depends(get_current_tenant)
):
    """Record a metric from an engine, tagged to the calling tenant"""
    metric = MetricPoint(
        timestamp=datetime.utcnow(),
        metric_type=metric_type,
        value=value,
        engine=engine,
        workflow_id=workflow_id,
        tenant_id=tenant.tenant_id
    )
    metrics_aggregator.add_metric(metric)

    return {
        "status": "recorded",
        "metric": metric.to_dict()
    }


@router.post("/metrics/batch")
async def record_metrics_batch(metrics_data: dict, tenant: Tenant = Depends(get_current_tenant)):
    """Record multiple metrics at once, tagged to the calling tenant"""
    recorded = []

    for metric_info in metrics_data.get("metrics", []):
        metric = MetricPoint(
            timestamp=datetime.fromisoformat(metric_info.get("timestamp", datetime.utcnow().isoformat())),
            metric_type=MetricType(metric_info["metric_type"]),
            value=metric_info["value"],
            engine=metric_info["engine"],
            workflow_id=metric_info.get("workflow_id"),
            context=metric_info.get("context", {}),
            tenant_id=tenant.tenant_id
        )
        metrics_aggregator.add_metric(metric)
        recorded.append(metric.to_dict())

    return {
        "status": "batch_recorded",
        "count": len(recorded),
        "metrics": recorded
    }


@router.get("/metrics/{workflow_id}")
async def get_metrics(
    workflow_id: str,
    metric_type: Optional[str] = None,
    hours: int = Query(24, ge=1, le=720),
    tenant: Tenant = Depends(get_current_tenant)
):
    """Get metrics for a workflow owned by the calling tenant"""
    start_time = datetime.utcnow() - timedelta(hours=hours)

    metrics = metrics_aggregator.get_metrics(
        workflow_id,
        metric_type=MetricType(metric_type) if metric_type else None,
        start_time=start_time,
        tenant_id=tenant.tenant_id
    )

    return {
        "workflow_id": workflow_id,
        "period_hours": hours,
        "metric_count": len(metrics),
        "metrics": [m.to_dict() for m in metrics]
    }


@router.get("/analysis/{workflow_id}")
async def analyze_workflow(
    workflow_id: str, hours: int = Query(24, ge=1, le=720),
    tenant: Tenant = Depends(get_current_tenant)
):
    """Analyze workflow performance for the calling tenant"""
    analysis = metrics_aggregator.analyze_performance(workflow_id, hours, tenant_id=tenant.tenant_id)

    return {
        "workflow_id": workflow_id,
        "period_hours": hours,
        "analysis": analysis.to_dict()
    }


@router.post("/optimize/{workflow_id}")
async def optimize_workflow(
    workflow_id: str, hours: int = Query(24, ge=1, le=720),
    tenant: Tenant = Depends(get_current_tenant)
):
    """Analyze and generate optimization for a workflow owned by the calling tenant"""
    decision = optimization_engine.analyze_and_optimize(workflow_id, hours, tenant_id=tenant.tenant_id)

    return {
        "workflow_id": workflow_id,
        "decision": decision.to_dict()
    }


@router.get("/opportunities")
async def get_optimization_opportunities(
    limit: int = Query(5, ge=1, le=20),
    tenant: Tenant = Depends(get_current_tenant)
):
    """Get the calling tenant's top optimization opportunities"""
    opportunities = optimization_engine.get_top_opportunities(limit, tenant_id=tenant.tenant_id)

    return {
        "count": len(opportunities),
        "opportunities": [opp.to_dict() for opp in opportunities]
    }


@router.get("/recommendations")
async def get_workflow_recommendations(
    workflow_ids: Optional[str] = Query(None, description="Comma-separated workflow IDs"),
    tenant: Tenant = Depends(get_current_tenant)
):
    """Get optimization recommendations for the calling tenant's workflows"""

    if workflow_ids:
        workflows = [{"id": wf_id.strip()} for wf_id in workflow_ids.split(",")]
    else:
        # Get all workflows with history, for this tenant only
        tenant_history = optimization_engine.execution_history.get(tenant.tenant_id, {})
        workflows = [{"id": wf_id} for wf_id in tenant_history.keys()]

    sequence = optimization_engine.recommend_workflow_sequence(workflows, tenant_id=tenant.tenant_id)

    return {
        "recommended_sequence": sequence,
        "count": len(sequence),
        "details": [
            {
                "workflow_id": wf_id,
                "priority": i + 1,
                "should_run": optimization_engine.should_run_workflow(wf_id, tenant_id=tenant.tenant_id)
            }
            for i, wf_id in enumerate(sequence)
        ]
    }


@router.get("/history/{workflow_id}")
async def get_optimization_history(workflow_id: str, tenant: Tenant = Depends(get_current_tenant)):
    """Get optimization decision history for a workflow owned by the calling tenant"""
    history = optimization_engine.get_execution_history(workflow_id, tenant_id=tenant.tenant_id)

    return {
        "workflow_id": workflow_id,
        "decision_count": len(history),
        "decisions": [d.to_dict() for d in history]
    }


@router.get("/status")
async def get_optimization_status(tenant: Tenant = Depends(get_current_tenant)):
    """Get optimization system status, scoped to the calling tenant"""
    tenant_metrics = sum(1 for m in metrics_aggregator.metrics if m.tenant_id == tenant.tenant_id)
    tenant_decisions = sum(1 for d in optimization_engine.decisions if d.tenant_id == tenant.tenant_id)

    return {
        "tenant_id": tenant.tenant_id,
        "total_metrics_recorded": tenant_metrics,
        "workflows_analyzed": len(optimization_engine.execution_history.get(tenant.tenant_id, {})),
        "total_decisions": tenant_decisions,
        "system_status": "healthy"
    }
