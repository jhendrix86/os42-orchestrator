"""
Tenant management routes for OS42 multi-tenancy

Provisioning and listing are admin-gated (X-Admin-Key); a tenant can look
up its own record with its own API key.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.models.tenant import Tenant
from app.services.tenancy import get_current_tenant, registry, require_admin

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", dependencies=[Depends(require_admin)])
async def create_tenant(name: str, tenant_id: Optional[str] = None, plan: str = "standard"):
    """Provision a new tenant and issue its API key (admin only)"""
    try:
        tenant = registry.register(name=name, tenant_id=tenant_id, plan=plan)
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
