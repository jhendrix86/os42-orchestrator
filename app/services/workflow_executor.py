"""
Workflow execution engine

Executes workflows by orchestrating calls to various engines
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import re
import httpx
import structlog

from app.config import engine_auth_headers

logger = structlog.get_logger()


class WorkflowExecutor:
    """Executes workflow definitions by calling orchestrated engines"""

    def __init__(self, engine_urls: Dict[str, str], client: Optional[httpx.AsyncClient] = None):
        self.engine_urls = engine_urls
        # Tests inject an httpx.AsyncClient bound to an ASGITransport so
        # engine calls hit an in-process fake instead of the network.
        self._owns_client = client is None
        self.client = client

    async def connect(self):
        """Create async HTTP client, unless one was already injected"""
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=30.0)

    async def disconnect(self):
        """Close async HTTP client, unless it was injected (caller owns it)"""
        if self.client and self._owns_client:
            await self.client.aclose()

    async def execute_workflow(
        self,
        workflow_id: str,
        definition: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a workflow definition

        Args:
            workflow_id: Unique workflow identifier
            definition: Workflow definition with steps
            context: Initial context/state for the workflow

        Returns:
            Workflow execution result
        """
        if not self.client:
            raise RuntimeError("Executor not connected. Call connect() first.")

        logger.info("workflow_execution_started", workflow_id=workflow_id)

        context = context or {}
        results = {}
        start_time = datetime.utcnow()

        try:
            steps = definition.get("steps", [])

            for i, step in enumerate(steps):
                step_id = step.get("id", f"step_{i}")
                engine = step.get("engine")
                action = step.get("action")
                params = step.get("params", {})

                logger.info(
                    "workflow_step_executing",
                    workflow_id=workflow_id,
                    step_id=step_id,
                    engine=engine,
                    action=action
                )

                # Resolve parameters (can reference previous step results)
                resolved_params = self._resolve_params(params, results)
                # Real engine endpoints are resource-scoped (e.g.
                # /content/{id}/repurpose) - a $steps.x.y reference embedded
                # in the action string itself resolves the same way params do.
                resolved_action = self._resolve_action_path(action, results)

                # Call the engine
                try:
                    result = await self._call_engine(
                        engine=engine,
                        action=resolved_action,
                        params=resolved_params
                    )

                    results[step_id] = result
                    logger.info(
                        "workflow_step_completed",
                        workflow_id=workflow_id,
                        step_id=step_id
                    )

                except Exception as e:
                    logger.error(
                        "workflow_step_failed",
                        workflow_id=workflow_id,
                        step_id=step_id,
                        error=str(e)
                    )

                    if step.get("on_error") == "stop":
                        raise

                    results[step_id] = {"error": str(e), "status": "failed"}

            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

            return {
                "workflow_id": workflow_id,
                "status": "completed",
                "steps": len(steps),
                "results": results,
                "started_at": start_time.isoformat(),
                "completed_at": end_time.isoformat(),
                "duration_seconds": duration
            }

        except Exception as e:
            logger.error("workflow_execution_failed", workflow_id=workflow_id, error=str(e))
            return {
                "workflow_id": workflow_id,
                "status": "failed",
                "error": str(e),
                "results": results,
                "started_at": start_time.isoformat(),
                "completed_at": datetime.utcnow().isoformat()
            }

    async def _call_engine(
        self,
        engine: str,
        action: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call a specific engine

        Args:
            engine: Engine name (content, marketing, etc.)
            action: Action to perform
            params: Parameters for the action

        Returns:
            Engine response
        """
        if engine not in self.engine_urls:
            raise ValueError(f"Unknown engine: {engine}")

        url = self.engine_urls[engine]
        endpoint = f"{url}/{action}"

        logger.info("engine_call", engine=engine, action=action, endpoint=endpoint)

        response = await self.client.post(endpoint, json=params, headers=engine_auth_headers())
        response.raise_for_status()

        return response.json()

    def _resolve_params(
        self,
        params: Dict[str, Any],
        results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Resolve parameter references to previous results

        Example: {"content_id": "$steps.create_content.id"}
                 → {"content_id": "123"}
        """
        resolved = {}

        for key, value in params.items():
            if isinstance(value, str) and value.startswith("$steps."):
                # Reference to a previous step result
                ref_path = value[7:]  # Remove "$steps."
                step_id, field = ref_path.split(".", 1)

                if step_id in results:
                    resolved[key] = results[step_id].get(field)
                else:
                    logger.warning(
                        "parameter_resolution_failed",
                        key=key,
                        reference=value,
                        step_id=step_id
                    )
                    resolved[key] = None
            else:
                resolved[key] = value

        return resolved

    # Matches $steps.step_id.field, same 2-part scheme as _resolve_params -
    # deliberately not the test fixtures' deeper nested-field syntax, to stay
    # consistent with what this class's own params resolution actually does.
    _ACTION_REF_PATTERN = re.compile(r"\$steps\.(\w+)\.(\w+)")

    def _resolve_action_path(self, action: str, results: Dict[str, Any]) -> str:
        """
        Substitute $steps.step_id.field references embedded in an action
        path string, for real engines whose endpoints are resource-scoped
        by ID rather than taking the ID as a body param.

        Example: "content/$steps.create_pillar.id/repurpose"
                 -> "content/3f2a.../repurpose"
        """

        def replace(match: "re.Match[str]") -> str:
            step_id, field = match.group(1), match.group(2)
            if step_id not in results:
                logger.warning(
                    "action_path_resolution_failed",
                    action=action, reference=match.group(0), step_id=step_id
                )
                return match.group(0)
            value = results[step_id].get(field)
            return str(value) if value is not None else match.group(0)

        return self._ACTION_REF_PATTERN.sub(replace, action)
