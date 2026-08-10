"""
Tenant model for OS42 multi-tenancy
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict


@dataclass
class Tenant:
    """A tenant (customer/workspace) operating on the OS42 orchestrator"""
    tenant_id: str
    name: str
    api_key: str
    plan: str = "standard"
    # Business objective biasing how OptimizationEngine.recommend_workflow_sequence
    # prioritizes this tenant's workflows - see optimization_engine.GOAL_ACTION_BONUS.
    goal: str = "balanced"
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for API responses. Never include api_key here."""
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "plan": self.plan,
            "goal": self.goal,
            "created_at": self.created_at.isoformat(),
        }
