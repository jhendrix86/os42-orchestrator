"""
Decision execution for OS42 Orchestrator

Closes the loop between OptimizationEngine's recommendations and actual
system behavior. A decision either:
  - changes orchestrator-internal state directly (PAUSE/RESUME - whether
    the orchestrator keeps scheduling this workflow), or
  - is handed to the engine that owns it (SCALE_BUDGET -> marketing,
    CHANGE_FORMAT -> content, etc) as an HTTP call.

Engine calls are best-effort: an engine being unreachable is expected in
dev/test (see WorkflowExecutor's own per-step error handling for
precedent) and is reported back as a failed ExecutionResult rather than
raised.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import httpx
import structlog

from app.services.metrics_aggregator import OptimizationAction
from app.services.optimization_engine import OptimizationDecision

logger = structlog.get_logger()

# Which engine owns each optimization action, and which endpoint on that
# engine applies it. PAUSE/RESUME are handled separately - they never
# leave the orchestrator.
ACTION_ENGINE_MAP: Dict[OptimizationAction, Tuple[str, str]] = {
    OptimizationAction.SCALE_BUDGET: ("marketing", "scale_budget"),
    OptimizationAction.INCREASE_FREQUENCY: ("marketing", "adjust_frequency"),
    OptimizationAction.DECREASE_FREQUENCY: ("marketing", "adjust_frequency"),
    OptimizationAction.CHANGE_FORMAT: ("content", "change_format"),
    OptimizationAction.CHANGE_CHANNEL: ("marketing", "change_channel"),
    OptimizationAction.ADJUST_TIMING: ("marketing", "adjust_timing"),
}


@dataclass
class ExecutionResult:
    """Outcome of applying a single OptimizationDecision"""
    workflow_id: str
    tenant_id: str
    action: OptimizationAction
    status: str  # "applied" | "failed" | "skipped"
    detail: str
    engine_called: Optional[str] = None
    applied_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "tenant_id": self.tenant_id,
            "action": self.action,
            "status": self.status,
            "detail": self.detail,
            "engine_called": self.engine_called,
            "applied_at": self.applied_at.isoformat(),
        }


class DecisionExecutor:
    """Applies OptimizationDecisions: local state changes or engine calls"""

    def __init__(self, engine_urls: Dict[str, str], client: Optional[httpx.AsyncClient] = None):
        self.engine_urls = engine_urls
        # Tests inject an httpx.AsyncClient bound to an ASGITransport so
        # engine calls hit an in-process fake instead of the network.
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(timeout=10.0)

    async def aclose(self):
        if self._owns_client:
            await self.client.aclose()

    async def apply(
        self, decision: OptimizationDecision, workflow: Optional[Dict[str, Any]]
    ) -> ExecutionResult:
        """
        Apply a decision. For PAUSE/RESUME, mutates `workflow["status"]`
        in place when a workflow record is provided. For engine-owned
        actions, calls the owning engine with the decision's parameters.
        """

        if decision.action == OptimizationAction.PAUSE:
            if workflow is not None:
                workflow["status"] = "paused"
            return ExecutionResult(
                workflow_id=decision.workflow_id, tenant_id=decision.tenant_id,
                action=decision.action, status="applied",
                detail=(
                    "Workflow marked paused; orchestrator will skip it in future scheduling."
                    if workflow is not None else
                    "No local workflow record to update, but future scheduling will skip this workflow_id."
                ),
            )

        if decision.action == OptimizationAction.RESUME:
            if workflow is not None:
                workflow["status"] = "active"
            return ExecutionResult(
                workflow_id=decision.workflow_id, tenant_id=decision.tenant_id,
                action=decision.action, status="applied",
                detail=(
                    "Workflow marked active."
                    if workflow is not None else
                    "No local workflow record to update."
                ),
            )

        mapping = ACTION_ENGINE_MAP.get(decision.action)
        if not mapping:
            return ExecutionResult(
                workflow_id=decision.workflow_id, tenant_id=decision.tenant_id,
                action=decision.action, status="skipped",
                detail=f"No engine mapping for action '{decision.action}'.",
            )

        engine, endpoint = mapping
        engine_url = self.engine_urls.get(engine)
        if not engine_url:
            return ExecutionResult(
                workflow_id=decision.workflow_id, tenant_id=decision.tenant_id,
                action=decision.action, status="failed", engine_called=engine,
                detail=f"Unknown engine '{engine}' - not in engine registry.",
            )

        payload = {
            "workflow_id": decision.workflow_id,
            "tenant_id": decision.tenant_id,
            **decision.parameters,
        }

        try:
            response = await self.client.post(f"{engine_url}/{endpoint}", json=payload)
            response.raise_for_status()
            return ExecutionResult(
                workflow_id=decision.workflow_id, tenant_id=decision.tenant_id,
                action=decision.action, status="applied", engine_called=engine,
                detail=f"{engine}/{endpoint} accepted the change.",
            )
        except httpx.HTTPError as e:
            logger.error(
                "decision_execution_failed",
                workflow_id=decision.workflow_id, tenant_id=decision.tenant_id,
                engine=engine, error=str(e)
            )
            return ExecutionResult(
                workflow_id=decision.workflow_id, tenant_id=decision.tenant_id,
                action=decision.action, status="failed", engine_called=engine,
                detail=f"Call to {engine}/{endpoint} failed: {e}",
            )
