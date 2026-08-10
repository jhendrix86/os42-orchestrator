"""
Shared recommend+apply logic for OS42 Orchestrator

Generates a fresh optimization decision for a single workflow and applies
it immediately. Used by both the HTTP apply endpoint
(POST /optimization/optimize/{id}/apply) and the autonomous scheduler, so
manual and autonomous triggering can never drift apart.
"""

from typing import Any, Dict, Optional

from app.services.decision_executor import DecisionExecutor, ExecutionResult
from app.services.optimization_engine import OptimizationDecision, OptimizationEngine


async def optimize_and_apply(
    optimization_engine: OptimizationEngine,
    engine_urls: Dict[str, str],
    tenant_id: str,
    workflow_id: str,
    workflow: Optional[Dict[str, Any]],
    hours: int = 24,
) -> Dict[str, Any]:
    """
    Analyze a workflow, decide what to do, and do it - in one call.
    Mutates `workflow["applied_decisions"]` in place when a workflow
    record is provided.
    """
    decision: OptimizationDecision = optimization_engine.analyze_and_optimize(
        workflow_id, hours, tenant_id=tenant_id
    )

    executor = DecisionExecutor(engine_urls=engine_urls)
    try:
        result: ExecutionResult = await executor.apply(decision, workflow)
    finally:
        await executor.aclose()

    if workflow is not None:
        workflow.setdefault("applied_decisions", []).append({
            "decision": decision.to_dict(),
            "result": result.to_dict(),
        })

    return {"decision": decision, "result": result}
