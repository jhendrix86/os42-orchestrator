"""
OS42 Orchestrator - Main Service

Central coordination layer that orchestrates all OS42 engines as a unified system.
Runs real business workflows: content creation → distribution → monetization → analysis
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import structlog
from datetime import datetime
from typing import Dict, Any, Optional
from app.routes.dashboard import router as dashboard_router

logger = structlog.get_logger()

# Engine service URLs (configurable via environment)
ENGINE_URLS = {
    "content": os.getenv("CONTENT_ENGINE_URL", "http://localhost:8038"),
    "marketing": os.getenv("MARKETING_ENGINE_URL", "http://localhost:8039"),
    "analytics": os.getenv("ANALYTICS_ENGINE_URL", "http://localhost:8042"),
    "monitoring": os.getenv("MONITORING_ENGINE_URL", "http://localhost:8044"),
    "notification": os.getenv("NOTIFICATION_ENGINE_URL", "http://localhost:8045"),
    "sales": os.getenv("SALES_ENGINE_URL", "http://localhost:8041"),
    "revenue": os.getenv("REVENUE_ENGINE_URL", "http://localhost:8036"),
    "integration": os.getenv("INTEGRATION_ENGINE_URL", "http://localhost:8040"),
    "pricing": os.getenv("PRICING_ENGINE_URL", "http://localhost:8047"),
    "support": os.getenv("SUPPORT_ENGINE_URL", "http://localhost:8037"),
    "governance": os.getenv("GOVERNANCE_ENGINE_URL", "http://localhost:8043"),
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("os42_orchestrator_starting")

    # Initialize global state
    app.state.system_status = "healthy"
    app.state.active_workflows = {}
    app.state.workflow_results = {}

    yield

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
    """Get overall system status"""
    return {
        "system_status": app.state.system_status,
        "active_workflows": len(app.state.active_workflows),
        "completed_workflows": len(app.state.workflow_results),
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
async def create_workflow(workflow_id: str, definition: Dict[str, Any]):
    """Create a new workflow"""
    try:
        app.state.active_workflows[workflow_id] = {
            "id": workflow_id,
            "definition": definition,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "steps": []
        }

        logger.info(
            "workflow_created",
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
async def get_workflow(workflow_id: str):
    """Get workflow status and results"""
    if workflow_id not in app.state.active_workflows and \
       workflow_id not in app.state.workflow_results:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow = app.state.active_workflows.get(workflow_id) or \
               app.state.workflow_results.get(workflow_id)

    return workflow


@app.get("/workflows")
async def list_workflows():
    """List all workflows"""
    return {
        "active_workflows": list(app.state.active_workflows.values()),
        "completed_workflows": list(app.state.workflow_results.values()),
        "total": len(app.state.active_workflows) + len(app.state.workflow_results)
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
            "active_workflows": len(app.state.active_workflows)
        }
    }


@app.get("/dashboard/activity")
async def dashboard_activity():
    """Get recent activity for the dashboard"""
    return {
        "recent_workflows": list(app.state.active_workflows.values())[:5],
        "recent_errors": [],
        "system_events": []
    }


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
