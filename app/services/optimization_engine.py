"""
Optimization engine - Makes autonomous decisions to improve performance

Uses metrics analysis to decide which workflows to run, how often, with what budget
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json

from app.services.metrics_aggregator import MetricsAggregator, PerformanceAnalysis, OptimizationAction


@dataclass
class OptimizationDecision:
    """A decision to optimize a workflow"""
    workflow_id: str
    timestamp: datetime
    action: OptimizationAction
    reason: str
    confidence: float  # 0-1, how confident we are
    estimated_impact: Optional[float] = None  # % improvement expected
    parameters: Dict[str, Any] = field(default_factory=dict)
    tenant_id: str = "default"

    def to_dict(self):
        return {
            "workflow_id": self.workflow_id,
            "tenant_id": self.tenant_id,
            "timestamp": self.timestamp.isoformat(),
            "action": self.action,
            "reason": self.reason,
            "confidence": self.confidence,
            "estimated_impact": self.estimated_impact,
            "parameters": self.parameters
        }


class OptimizationEngine:
    """Makes autonomous optimization decisions based on metrics"""

    def __init__(self, metrics_aggregator: MetricsAggregator):
        self.metrics = metrics_aggregator
        self.decisions: List[OptimizationDecision] = []
        # tenant_id -> workflow_id -> decisions, mirroring MetricsAggregator's
        # nested layout so a tenant can never read another tenant's history.
        self.execution_history: Dict[str, Dict[str, List[OptimizationDecision]]] = {}

    def restore(self, decision: OptimizationDecision) -> None:
        """Insert an already-made decision, as when loading from a persistence snapshot"""
        self.decisions.append(decision)
        tenant_history = self.execution_history.setdefault(decision.tenant_id, {})
        tenant_history.setdefault(decision.workflow_id, []).append(decision)

    def analyze_and_optimize(self, workflow_id: str, period_hours: int = 24,
                              tenant_id: str = "default") -> OptimizationDecision:
        """Analyze workflow and generate optimization decision"""

        analysis = self.metrics.analyze_performance(workflow_id, period_hours, tenant_id=tenant_id)

        decision = self._make_decision(analysis)

        # Track decision
        self.decisions.append(decision)
        tenant_history = self.execution_history.setdefault(tenant_id, {})
        tenant_history.setdefault(workflow_id, []).append(decision)

        return decision

    def _make_decision(self, analysis: PerformanceAnalysis) -> OptimizationDecision:
        """Generate optimization decision from analysis"""
        tenant_id = analysis.tenant_id

        # Rule 1: High conversion rate → Scale budget
        if analysis.conversion_rate and analysis.conversion_rate > 0.05:
            return OptimizationDecision(
                workflow_id=analysis.workflow_id,
                tenant_id=tenant_id,
                timestamp=datetime.utcnow(),
                action=OptimizationAction.SCALE_BUDGET,
                reason="High conversion rate (>5%) detected. Scale to capture more market.",
                confidence=0.9,
                estimated_impact=0.30,
                parameters={"budget_increase_percent": 50}
            )

        # Rule 2: Improving trend + good engagement → Increase frequency
        if analysis.conversion_trend == "improving" and analysis.engagement_rate and analysis.engagement_rate > 0.05:
            return OptimizationDecision(
                workflow_id=analysis.workflow_id,
                tenant_id=tenant_id,
                timestamp=datetime.utcnow(),
                action=OptimizationAction.INCREASE_FREQUENCY,
                reason="Positive trend with strong engagement. Run more frequently.",
                confidence=0.8,
                estimated_impact=0.20,
                parameters={"frequency_increase_percent": 25}
            )

        # Rule 3: Declining trend → Pause and investigate
        if analysis.conversion_trend == "declining":
            return OptimizationDecision(
                workflow_id=analysis.workflow_id,
                tenant_id=tenant_id,
                timestamp=datetime.utcnow(),
                action=OptimizationAction.PAUSE,
                reason="Declining conversion trend. Pause to prevent wasting budget.",
                confidence=0.7,
                estimated_impact=-0.10,
                parameters={"reason": "performance decline"}
            )

        # Rule 4: High error rate → Pause pending fix
        if analysis.error_rate and analysis.error_rate > 0.10:
            return OptimizationDecision(
                workflow_id=analysis.workflow_id,
                tenant_id=tenant_id,
                timestamp=datetime.utcnow(),
                action=OptimizationAction.PAUSE,
                reason="High error rate (>10%). System needs attention.",
                confidence=0.95,
                estimated_impact=0.0,
                parameters={"reason": "high error rate"}
            )

        # Rule 5: Low engagement → Change format
        if analysis.engagement_rate and analysis.engagement_rate < 0.01:
            return OptimizationDecision(
                workflow_id=analysis.workflow_id,
                tenant_id=tenant_id,
                timestamp=datetime.utcnow(),
                action=OptimizationAction.CHANGE_FORMAT,
                reason="Very low engagement (<1%). Try different content format.",
                confidence=0.7,
                estimated_impact=0.15,
                parameters={"formats_to_try": ["video", "interactive", "infographic"]}
            )

        # Rule 6: Slow response times → Optimize
        if analysis.avg_response_time and analysis.avg_response_time > 2000:
            return OptimizationDecision(
                workflow_id=analysis.workflow_id,
                tenant_id=tenant_id,
                timestamp=datetime.utcnow(),
                action=OptimizationAction.ADJUST_TIMING,
                reason="Slow response times (>2s). Defer to off-peak hours.",
                confidence=0.6,
                estimated_impact=0.10,
                parameters={"adjust_schedule": True}
            )

        # Default: Monitor and hold
        return OptimizationDecision(
            workflow_id=analysis.workflow_id,
            tenant_id=tenant_id,
            timestamp=datetime.utcnow(),
            action=OptimizationAction.RESUME,  # Continue as-is
            reason="Performance stable. Continue monitoring.",
            confidence=0.8,
            estimated_impact=0.0,
            parameters={}
        )

    def get_top_opportunities(self, limit: int = 5, tenant_id: str = "default") -> List[OptimizationDecision]:
        """Get workflows with highest optimization potential, scoped to a single tenant"""

        # Rank by estimated impact * confidence
        scored = []
        for decision in self.decisions:
            if decision.tenant_id != tenant_id:
                continue
            if decision.estimated_impact:
                score = decision.estimated_impact * decision.confidence
                scored.append((score, decision))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        return [d for _, d in scored[:limit]]

    def recommend_workflow_sequence(self, available_workflows: List[Dict[str, Any]],
                                     tenant_id: str = "default") -> List[str]:
        """Recommend order to run workflows for maximum daily impact, scoped to a single tenant"""

        # Score each workflow
        workflow_scores: Dict[str, float] = {}
        tenant_history = self.execution_history.get(tenant_id, {})

        for workflow in available_workflows:
            workflow_id = workflow["id"]

            # Get latest analysis
            latest_decisions = tenant_history.get(workflow_id, [])
            if not latest_decisions:
                # No history, default score
                workflow_scores[workflow_id] = 0.5
                continue

            latest = latest_decisions[-1]

            # Base score on confidence and impact
            base_score = latest.confidence
            if latest.estimated_impact:
                base_score *= (1 + latest.estimated_impact)

            # Adjust for action type
            action_bonus = {
                OptimizationAction.SCALE_BUDGET: 1.0,
                OptimizationAction.INCREASE_FREQUENCY: 0.8,
                OptimizationAction.CHANGE_FORMAT: 0.5,
                OptimizationAction.ADJUST_TIMING: 0.3,
                OptimizationAction.PAUSE: -1.0,
                OptimizationAction.RESUME: 0.0,
                OptimizationAction.CHANGE_CHANNEL: 0.4,
                OptimizationAction.DECREASE_FREQUENCY: -0.5,
            }

            adjusted_score = base_score + action_bonus.get(latest.action, 0)
            workflow_scores[workflow_id] = max(0, adjusted_score)

        # Sort by score descending
        sorted_workflows = sorted(workflow_scores.items(), key=lambda x: x[1], reverse=True)

        return [wf_id for wf_id, _ in sorted_workflows]

    def get_execution_history(self, workflow_id: str, tenant_id: str = "default") -> List[OptimizationDecision]:
        """Get optimization history for a workflow, scoped to a single tenant"""
        return self.execution_history.get(tenant_id, {}).get(workflow_id, [])

    def should_run_workflow(self, workflow_id: str, tenant_id: str = "default") -> bool:
        """Determine if a workflow should run based on latest decision"""

        latest_decisions = self.get_execution_history(workflow_id, tenant_id=tenant_id)
        if not latest_decisions:
            return True  # No history, should run

        latest = latest_decisions[-1]

        # Only skip if explicitly paused
        return latest.action != OptimizationAction.PAUSE
