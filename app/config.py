"""
OS42 Orchestrator configuration - engine service registry

Split out from main.py so other modules (e.g. routes/optimization.py's
decision-execution endpoint) can reach engine URLs without importing
main.py itself and creating a circular import.
"""

import os
from typing import Dict

ENGINE_URLS: Dict[str, str] = {
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
