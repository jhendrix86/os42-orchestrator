"""
Tenant registry and API-key authentication for OS42 multi-tenancy

In-memory registry, matching the rest of the orchestrator's services
(no persistence layer yet - see PHASE_B_COMPLETION.md tech debt notes).
Swap for a database-backed store when the orchestrator gets real
persistence.
"""

import hmac
import os
import secrets
from typing import Dict, List, Optional

import structlog
from fastapi import Header, HTTPException, status

from app.models.tenant import Tenant

logger = structlog.get_logger()


class TenantRegistry:
    """In-memory tenant directory keyed by tenant_id and api_key"""

    def __init__(self):
        self._by_id: Dict[str, Tenant] = {}
        self._by_key: Dict[str, Tenant] = {}

    def register(
        self,
        name: str,
        tenant_id: Optional[str] = None,
        api_key: Optional[str] = None,
        plan: str = "standard",
    ) -> Tenant:
        """Provision a new tenant. Raises ValueError if tenant_id is taken."""
        tenant_id = tenant_id or name.lower().replace(" ", "-")
        if tenant_id in self._by_id:
            raise ValueError(f"Tenant '{tenant_id}' already exists")

        api_key = api_key or f"os42_{secrets.token_urlsafe(24)}"
        tenant = Tenant(tenant_id=tenant_id, name=name, api_key=api_key, plan=plan)

        self._by_id[tenant.tenant_id] = tenant
        self._by_key[tenant.api_key] = tenant
        return tenant

    def get(self, tenant_id: str) -> Optional[Tenant]:
        return self._by_id.get(tenant_id)

    def get_by_api_key(self, api_key: str) -> Optional[Tenant]:
        return self._by_key.get(api_key)

    def list(self) -> List[Tenant]:
        return list(self._by_id.values())


registry = TenantRegistry()

# Seed a default tenant so the system is usable out of the box in dev/test,
# and so Phase A/B code that predates multi-tenancy keeps working. Override
# via env vars for anything beyond local development.
_DEFAULT_TENANT_ID = os.getenv("OS42_DEFAULT_TENANT_ID", "default")
_DEFAULT_API_KEY = os.getenv("OS42_DEFAULT_API_KEY", "os42_dev_default_key")
registry.register(name="Default Tenant", tenant_id=_DEFAULT_TENANT_ID, api_key=_DEFAULT_API_KEY)

ADMIN_KEY = os.getenv("OS42_ADMIN_KEY", "os42_dev_admin_key")

logger.info(
    "tenancy_initialized",
    default_tenant_id=_DEFAULT_TENANT_ID,
    default_api_key=_DEFAULT_API_KEY,
    note="override OS42_DEFAULT_API_KEY / OS42_ADMIN_KEY outside dev",
)


async def get_current_tenant(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> Tenant:
    """Resolve the calling tenant from the X-API-Key header"""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    tenant = registry.get_by_api_key(x_api_key)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return tenant


async def require_admin(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key")
) -> None:
    """Guard for orchestrator-admin-only endpoints (e.g. tenant provisioning)"""
    if not x_admin_key or not hmac.compare_digest(x_admin_key, ADMIN_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin key",
        )
