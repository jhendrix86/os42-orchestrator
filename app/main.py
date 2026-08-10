"""
OS42 Orchestrator - Main Service

Central coordination layer that orchestrates all OS42 engines as a unified system.
Runs real business workflows: content creation → distribution → monetization → analysis
"""

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import structlog
from datetime import datetime
from typing import Dict, Any, Optional
from app.config import ENGINE_URLS
from app.models.tenant import Tenant
from app.routes.dashboard import router as dashboard_router
from app.routes.optimization import router as optimization_router, optimization_engine, metrics_aggregator
from app.routes.tenants import router as tenants_router
from app.services.persistence import load_snapshot, save_snapshot
from app.services.scheduler import AutonomousScheduler
from app.services.tenancy import get_current_tenant, require_admin, registry as tenant_registry

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("os42_orchestrator_starting")

    # Initialize global state.
    # active_workflows / workflow_results are nested tenant_id -> workflow_id
    # -> workflow dicts, so tenants can never see each other's workflows even
    # if they happen to pick the same workflow_id.
    app.state.system_status = "healthy"
    app.state.active_workflows = {}
    app.state.workflow_results = {}

    # Persistence is opt-in (OS42_PERSISTENCE_PATH) - when unset this is a
    # no-op and behavior is identical to every prior phase, pure in-memory.
    if load_snapshot(tenant_registry, metrics_aggregator, optimization_engine,
                      app.state.active_workflows, app.state.workflow_results):
        logger.info("state_restored_from_snapshot")

    def _persist(_summary):
        save_snapshot(tenant_registry, metrics_aggregator, optimization_engine,
                       app.state.active_workflows, app.state.workflow_results)

    # Autonomous scheduler: periodically re-optimizes and applies decisions
    # for every tenant's active workflows, so nothing has to call
    # POST /optimization/optimize/{id}/apply by hand. Ticks immediately on
    # startup, then every interval_seconds. Also doubles as the persistence
    # heartbeat via on_tick, so a crash loses at most one interval's data.
    app.state.scheduler = AutonomousScheduler(
        optimization_engine=optimization_engine,
        engine_urls=ENGINE_URLS,
        get_active_workflows=lambda: app.state.active_workflows,
        interval_seconds=float(os.getenv("OS42_SCHEDULER_INTERVAL_SECONDS", "300")),
        on_tick=_persist,
    )
    app.state.scheduler.start()

    yield

    await app.state.scheduler.stop()
    save_snapshot(tenant_registry, metrics_aggregator, optimization_engine,
                   app.state.active_workflows, app.state.workflow_results)
    logger.info("os42_orchestrator_shutting_down")


# Create FastAPI application
app = FastAPI(
    title="OS42 Orchestrator",
    description="Central coordination layer for the Autonomous Business Operating System",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(dashboard_router)
app.include_router(optimization_router)
app.include_router(tenants_router)


# === Health & Status ===

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "service": "os42-orchestrator",
        "version": "1.0.0",
        "status": app.state.system_status,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/status")
async def system_status():
    """Get overall system status, across all tenants"""
    return {
        "system_status": app.state.system_status,
        "active_workflows": sum(len(wfs) for wfs in app.state.active_workflows.values()),
        "completed_workflows": sum(len(wfs) for wfs in app.state.workflow_results.values()),
        "tenants": len(app.state.active_workflows.keys() | app.state.workflow_results.keys()),
        "engines": {
            name: {"url": url, "status": "configured"}
            for name, url in ENGINE_URLS.items()
        },
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "OS42 Orchestrator",
        "version": "1.0.0",
        "description": "Central coordination layer for the Autonomous Business Operating System",
        "endpoints": {
            "health": "/health",
            "status": "/status",
            "workflows": "/workflows",
            "dashboard": "/dashboard",
            "docs": "/docs"
        },
        "engines": list(ENGINE_URLS.keys())
    }


# === Workflow Management ===

@app.post("/workflows/create")
async def create_workflow(
    workflow_id: str,
    definition: Dict[str, Any],
    tenant: Tenant = Depends(get_current_tenant)
):
    """Create a new workflow, scoped to the calling tenant"""
    try:
        tenant_workflows = app.state.active_workflows.setdefault(tenant.tenant_id, {})
        tenant_workflows[workflow_id] = {
            "id": workflow_id,
            "tenant_id": tenant.tenant_id,
            "definition": definition,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "steps": [],
            "applied_decisions": []
        }

        logger.info(
            "workflow_created",
            tenant_id=tenant.tenant_id,
            workflow_id=workflow_id,
            step_count=len(definition.get("steps", []))
        )

        return {
            "workflow_id": workflow_id,
            "status": "created",
            "message": f"Workflow {workflow_id} created successfully"
        }
    except Exception as e:
        logger.error("workflow_creation_failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str, tenant: Tenant = Depends(get_current_tenant)):
    """Get workflow status and results, scoped to the calling tenant"""
    tenant_active = app.state.active_workflows.get(tenant.tenant_id, {})
    tenant_results = app.state.workflow_results.get(tenant.tenant_id, {})

    if workflow_id not in tenant_active and workflow_id not in tenant_results:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return tenant_active.get(workflow_id) or tenant_results.get(workflow_id)


@app.get("/workflows")
async def list_workflows(tenant: Tenant = Depends(get_current_tenant)):
    """List all workflows owned by the calling tenant"""
    tenant_active = app.state.active_workflows.get(tenant.tenant_id, {})
    tenant_results = app.state.workflow_results.get(tenant.tenant_id, {})

    return {
        "active_workflows": list(tenant_active.values()),
        "completed_workflows": list(tenant_results.values()),
        "total": len(tenant_active) + len(tenant_results)
    }


# === Dashboard Data ===

@app.get("/dashboard/metrics")
async def dashboard_metrics():
    """Get metrics for the dashboard"""
    return {
        "content": {
            "published": 0,  # Will be populated by content-engine integration
            "repurposed": 0,
            "distribution_channels": ["WordPress", "dev.to", "Substack"]
        },
        "revenue": {
            "total": 0,  # Will be populated by revenue-operations-engine
            "trends": []
        },
        "audience": {
            "subscribers": 0,  # Will be populated by marketing-automation-engine
            "growth_rate": 0
        },
        "system": {
            "health": app.state.system_status,
            "engines_healthy": len(ENGINE_URLS),
            "active_workflows": sum(len(wfs) for wfs in app.state.active_workflows.values())
        }
    }


@app.get("/dashboard/activity")
async def dashboard_activity():
    """Get recent activity for the dashboard, across all tenants"""
    recent_workflows = [
        workflow
        for tenant_workflows in app.state.active_workflows.values()
        for workflow in tenant_workflows.values()
    ]
    return {
        "recent_workflows": recent_workflows[:5],
        "recent_errors": [],
        "system_events": []
    }


# === Autonomous Scheduler ===

@app.get("/scheduler/status")
async def scheduler_status():
    """Get autonomous scheduler status (system-wide operational info, not tenant data)"""
    return app.state.scheduler.status()


@app.post("/scheduler/pause", dependencies=[Depends(require_admin)])
async def scheduler_pause():
    """Stop the scheduler from applying decisions, without tearing down the loop (admin only)"""
    app.state.scheduler.pause()
    return {"status": "paused"}


@app.post("/scheduler/resume", dependencies=[Depends(require_admin)])
async def scheduler_resume():
    """Resume autonomous decision application (admin only)"""
    app.state.scheduler.resume()
    return {"status": "resumed"}


# === Service Discovery ===

@app.get("/services")
async def list_services():
    """List all registered services"""
    return {
        "services": ENGINE_URLS,
        "total": len(ENGINE_URLS)
    }


@app.get("/services/{service_name}/status")
async def service_status(service_name: str):
    """Check status of a specific service"""
    if service_name not in ENGINE_URLS:
        raise HTTPException(status_code=404, detail=f"Service {service_name} not found")

    # TODO: Actually call the service's /health endpoint
    return {
        "service": service_name,
        "url": ENGINE_URLS[service_name],
        "status": "healthy"  # Placeholder
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8050,
        reload=True
    )
