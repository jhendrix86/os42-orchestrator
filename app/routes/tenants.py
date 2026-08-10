"""
Tenant management routes for OS42 multi-tenancy

Provisioning and listing are admin-gated (X-Admin-Key); a tenant can look
up its own record with its own API key.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.models.tenant import Tenant
from app.services.optimization_engine import VALID_GOALS
from app.services.tenancy import get_current_tenant, registry, require_admin

router = APIRouter(prefix="/tenants", tags=["tenants"])


def _validate_goal(goal: str) -> None:
    if goal not in VALID_GOALS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid goal '{goal}'. Valid goals: {sorted(VALID_GOALS)}",
        )


@router.post("", dependencies=[Depends(require_admin)])
async def create_tenant(
    name: str, tenant_id: Optional[str] = None, plan: str = "standard", goal: str = "balanced"
):
    """Provision a new tenant and issue its API key (admin only)"""
    _validate_goal(goal)
    try:
        tenant = registry.register(name=name, tenant_id=tenant_id, plan=plan, goal=goal)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {
        **tenant.to_dict(),
        "api_key": tenant.api_key,  # returned once, at creation time only
    }


@router.get("", dependencies=[Depends(require_admin)])
async def list_tenants():
    """List all provisioned tenants (admin only)"""
    tenants = registry.list()
    return {"count": len(tenants), "tenants": [t.to_dict() for t in tenants]}


@router.get("/me")
async def get_my_tenant(tenant: Tenant = Depends(get_current_tenant)):
    """Look up the tenant identified by the caller's own API key"""
    return tenant.to_dict()


@router.put("/me/goal")
async def set_my_goal(goal: str, tenant: Tenant = Depends(get_current_tenant)):
    """
    Set the calling tenant's business objective. Biases how
    OptimizationEngine.recommend_workflow_sequence prioritizes this
    tenant's own workflows going forward - see GOAL_ACTION_BONUS.
    """
    _validate_goal(goal)
    tenant.goal = goal
    return tenant.to_dict()
