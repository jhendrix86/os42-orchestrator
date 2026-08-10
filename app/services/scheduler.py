"""
Autonomous scheduler for OS42 Orchestrator

Periodically re-evaluates every tenant's active workflows and applies
whatever optimization decision comes out. This is what makes the system
autonomous rather than requiring a human (or an external cron job) to call
POST /optimization/optimize/{id}/apply by hand for every workflow.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import structlog

from app.services.autopilot import optimize_and_apply
from app.services.optimization_engine import OptimizationEngine

logger = structlog.get_logger()

# tenant_id -> workflow_id -> workflow record
ActiveWorkflows = Dict[str, Dict[str, Dict[str, Any]]]


@dataclass
class TickSummary:
    """What happened during one autonomous pass"""
    started_at: datetime
    finished_at: datetime
    tenants_processed: int
    workflows_processed: int
    results: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        for r in self.results:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1

        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "tenants_processed": self.tenants_processed,
            "workflows_processed": self.workflows_processed,
            "results_by_status": by_status,
        }


class AutonomousScheduler:
    """Background loop that re-optimizes every tenant's active workflows"""

    def __init__(
        self,
        optimization_engine: OptimizationEngine,
        engine_urls: Dict[str, str],
        get_active_workflows: Callable[[], ActiveWorkflows],
        interval_seconds: float = 300.0,
        on_tick: Optional[Callable[["TickSummary"], None]] = None,
    ):
        self.optimization_engine = optimization_engine
        self.engine_urls = engine_urls
        self.get_active_workflows = get_active_workflows
        self.interval_seconds = interval_seconds
        # Optional hook fired after every tick (e.g. persisting a snapshot).
        # Kept generic on purpose - the scheduler doesn't need to know what
        # persistence is, just that something may want to react to a tick.
        self.on_tick = on_tick

        self._task: Optional[asyncio.Task] = None
        self._paused = False
        self.tick_count = 0
        self.last_tick: Optional[TickSummary] = None

    async def tick(self) -> TickSummary:
        """Run exactly one autonomous pass over every tenant's workflows"""
        started_at = datetime.utcnow()
        results: List[Dict[str, Any]] = []

        # Snapshot before iterating: an `await` inside the loop below yields
        # control back to the event loop, during which a concurrent request
        # (e.g. POST /workflows/create) could otherwise mutate these dicts
        # mid-iteration.
        tenants = {
            tenant_id: dict(workflows)
            for tenant_id, workflows in self.get_active_workflows().items()
        }

        for tenant_id, workflows in tenants.items():
            for workflow_id, workflow in workflows.items():
                outcome = await optimize_and_apply(
                    self.optimization_engine, self.engine_urls,
                    tenant_id, workflow_id, workflow,
                )
                results.append({
                    "tenant_id": tenant_id,
                    "workflow_id": workflow_id,
                    "action": outcome["decision"].action,
                    "status": outcome["result"].status,
                })

        summary = TickSummary(
            started_at=started_at,
            finished_at=datetime.utcnow(),
            tenants_processed=len(tenants),
            workflows_processed=sum(len(w) for w in tenants.values()),
            results=results,
        )
        self.tick_count += 1
        self.last_tick = summary
        logger.info(
            "scheduler_tick_complete",
            tick=self.tick_count,
            tenants=summary.tenants_processed,
            workflows=summary.workflows_processed,
        )

        if self.on_tick:
            try:
                self.on_tick(summary)
            except Exception as e:
                logger.error("scheduler_on_tick_hook_failed", error=str(e))

        return summary

    async def _run(self):
        while True:
            if not self._paused:
                try:
                    await self.tick()
                except Exception as e:
                    logger.error("scheduler_tick_failed", error=str(e))
            await asyncio.sleep(self.interval_seconds)

    def start(self):
        """Start the background loop. Safe to call more than once."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())
            logger.info("scheduler_started", interval_seconds=self.interval_seconds)

    async def stop(self):
        """Cancel the background loop and wait for it to actually stop."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("scheduler_stopped")

    def pause(self):
        """Stop applying decisions without tearing down the loop"""
        self._paused = True

    def resume(self):
        self._paused = False

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "paused": self._paused,
            "interval_seconds": self.interval_seconds,
            "tick_count": self.tick_count,
            "last_tick": self.last_tick.to_dict() if self.last_tick else None,
        }
