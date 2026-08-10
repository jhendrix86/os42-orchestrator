"""
Snapshot-based persistence for OS42 Orchestrator

Opt-in: disabled unless OS42_PERSISTENCE_PATH is set, in which case every
prior-phase test (none of which set it) runs exactly as before - pure
in-memory, nothing touches disk. When enabled, the orchestrator's state
(tenants, metrics, optimization decisions, workflows) is loaded from a JSON
snapshot on startup and saved back to it after each scheduler tick and on
clean shutdown (see main.py's lifespan and AutonomousScheduler's on_tick).

This is a snapshot, not a transaction log or a real database: a hard
crash between saves loses whatever changed since the last save, and there
is no concurrent-writer story. Good enough for a single dev/prototype
instance; a real deployment would want an actual database and
write-through persistence instead - see PHASE_D_COMPLETION.md tech debt.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

from app.models.tenant import Tenant
from app.services.metrics_aggregator import MetricPoint, MetricsAggregator, MetricType
from app.services.optimization_engine import OptimizationAction, OptimizationDecision, OptimizationEngine
from app.services.tenancy import TenantRegistry

logger = structlog.get_logger()

# None => persistence disabled (the default, and always the case in tests).
PERSISTENCE_PATH: Optional[str] = os.getenv("OS42_PERSISTENCE_PATH")

SNAPSHOT_VERSION = 1


def _tenant_to_row(t: Tenant) -> Dict[str, Any]:
    return {
        "tenant_id": t.tenant_id, "name": t.name, "api_key": t.api_key,
        "plan": t.plan, "created_at": t.created_at.isoformat(),
    }


def _metric_to_row(m: MetricPoint) -> Dict[str, Any]:
    return {
        "timestamp": m.timestamp.isoformat(), "metric_type": m.metric_type.value,
        "value": m.value, "engine": m.engine, "workflow_id": m.workflow_id,
        "tenant_id": m.tenant_id, "context": m.context,
    }


def _decision_to_row(d: OptimizationDecision) -> Dict[str, Any]:
    return {
        "workflow_id": d.workflow_id, "timestamp": d.timestamp.isoformat(),
        "action": d.action.value, "reason": d.reason, "confidence": d.confidence,
        "estimated_impact": d.estimated_impact, "parameters": d.parameters,
        "tenant_id": d.tenant_id,
    }


def build_snapshot(
    tenant_registry: TenantRegistry,
    metrics_aggregator: MetricsAggregator,
    optimization_engine: OptimizationEngine,
    active_workflows: Dict[str, Dict[str, Any]],
    workflow_results: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "version": SNAPSHOT_VERSION,
        "saved_at": datetime.utcnow().isoformat(),
        "tenants": [_tenant_to_row(t) for t in tenant_registry.list()],
        "metrics": [_metric_to_row(m) for m in metrics_aggregator.metrics],
        "decisions": [_decision_to_row(d) for d in optimization_engine.decisions],
        # Workflow records are already plain JSON-safe dicts (built from
        # request bodies and .to_dict() calls) - no conversion needed.
        "active_workflows": active_workflows,
        "workflow_results": workflow_results or {},
    }


def save_snapshot(
    tenant_registry: TenantRegistry,
    metrics_aggregator: MetricsAggregator,
    optimization_engine: OptimizationEngine,
    active_workflows: Dict[str, Dict[str, Any]],
    workflow_results: Optional[Dict[str, Dict[str, Any]]] = None,
    path: Optional[str] = None,
) -> Optional[str]:
    """Write current state to disk. No-op (returns None) if persistence is disabled."""
    target = path or PERSISTENCE_PATH
    if not target:
        return None

    snapshot = build_snapshot(
        tenant_registry, metrics_aggregator, optimization_engine, active_workflows, workflow_results
    )

    tmp_path = f"{target}.tmp"
    Path(tmp_path).write_text(json.dumps(snapshot, indent=2))
    os.replace(tmp_path, target)  # atomic on both POSIX and Windows

    logger.info(
        "snapshot_saved", path=target,
        tenants=len(snapshot["tenants"]), metrics=len(snapshot["metrics"]),
        decisions=len(snapshot["decisions"]),
    )
    return target


def load_snapshot(
    tenant_registry: TenantRegistry,
    metrics_aggregator: MetricsAggregator,
    optimization_engine: OptimizationEngine,
    active_workflows: Dict[str, Dict[str, Any]],
    workflow_results: Optional[Dict[str, Dict[str, Any]]] = None,
    path: Optional[str] = None,
) -> bool:
    """
    Restore state from disk into the given, already-constructed (and
    normally empty) singletons/dicts. Returns True if a snapshot was
    found and loaded, False otherwise - including when persistence is
    disabled or no snapshot file exists yet (e.g. first-ever startup).
    """
    target = path or PERSISTENCE_PATH
    if not target or not Path(target).exists():
        return False

    snapshot = json.loads(Path(target).read_text())

    for row in snapshot.get("tenants", []):
        tenant_registry.restore(Tenant(
            tenant_id=row["tenant_id"], name=row["name"], api_key=row["api_key"],
            plan=row["plan"], created_at=datetime.fromisoformat(row["created_at"]),
        ))

    for row in snapshot.get("metrics", []):
        metrics_aggregator.add_metric(MetricPoint(
            timestamp=datetime.fromisoformat(row["timestamp"]),
            metric_type=MetricType(row["metric_type"]), value=row["value"],
            engine=row["engine"], workflow_id=row["workflow_id"],
            tenant_id=row["tenant_id"], context=row.get("context", {}),
        ))

    for row in snapshot.get("decisions", []):
        optimization_engine.restore(OptimizationDecision(
            workflow_id=row["workflow_id"], timestamp=datetime.fromisoformat(row["timestamp"]),
            action=OptimizationAction(row["action"]), reason=row["reason"],
            confidence=row["confidence"], estimated_impact=row.get("estimated_impact"),
            parameters=row.get("parameters", {}), tenant_id=row["tenant_id"],
        ))

    for tenant_id, workflows in snapshot.get("active_workflows", {}).items():
        active_workflows[tenant_id] = workflows

    if workflow_results is not None:
        for tenant_id, workflows in snapshot.get("workflow_results", {}).items():
            workflow_results[tenant_id] = workflows

    logger.info(
        "snapshot_loaded", path=target,
        tenants=len(snapshot.get("tenants", [])), metrics=len(snapshot.get("metrics", [])),
        decisions=len(snapshot.get("decisions", [])),
    )
    return True
