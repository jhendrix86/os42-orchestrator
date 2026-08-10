"""
OS42 Orchestrator configuration - engine service registry

Split out from main.py so other modules (e.g. routes/optimization.py's
decision-execution endpoint) can reach engine URLs without importing
main.py itself and creating a circular import.

Ports below are cross-checked against C:\\Users\\Jonat\\CascadeProjects\\HANDOFF.md's
authoritative port map (2026-08-10 reconciliation) - 6 of these were
previously wrong, pointed at a different, live engine instead of the
intended one. See CLAUDE.md at the repo root for the full story.

`pricing-intelligence-system` is deliberately absent: it isn't an HTTP
service at all (a CLI batch-job runner, no FastAPI app), so it was never
a valid HTTP peer to register here.
"""

import os
from typing import Dict, Optional

ENGINE_URLS: Dict[str, str] = {
    "content": os.getenv("CONTENT_ENGINE_URL", "http://localhost:8040"),
    "marketing": os.getenv("MARKETING_ENGINE_URL", "http://localhost:8039"),
    "analytics": os.getenv("ANALYTICS_ENGINE_URL", "http://localhost:8042"),
    "monitoring": os.getenv("MONITORING_ENGINE_URL", "http://localhost:8043"),
    "notification": os.getenv("NOTIFICATION_ENGINE_URL", "http://localhost:8037"),
    "sales": os.getenv("SALES_ENGINE_URL", "http://localhost:8041"),
    "revenue": os.getenv("REVENUE_ENGINE_URL", "http://localhost:8036"),
    "integration": os.getenv("INTEGRATION_ENGINE_URL", "http://localhost:8044"),
    "support": os.getenv("SUPPORT_ENGINE_URL", "http://localhost:8038"),
    "governance": os.getenv("GOVERNANCE_ENGINE_URL", "http://localhost:8033"),
}

# content-engine, marketing-automation-engine, and revenue-operations-engine
# are already wired to unkey-auth (currently failing open - no real Unkey
# workspace/root key exists yet, per HANDOFF.md). None of these calls will
# be rejected today, but they'll start getting real 401s the moment a real
# UNKEY_ROOT_KEY is configured engine-side unless this is set too - this is
# the orchestrator's OWN key (verified by the engines), a different key
# from an engine's UNKEY_ROOT_KEY (which verifies everyone else's).
UNKEY_API_KEY: Optional[str] = os.getenv("UNKEY_API_KEY")


def engine_auth_headers() -> Dict[str, str]:
    """Bearer-token header for outbound engine calls, or {} if unconfigured."""
    if not UNKEY_API_KEY:
        return {}
    return {"Authorization": f"Bearer {UNKEY_API_KEY}"}
