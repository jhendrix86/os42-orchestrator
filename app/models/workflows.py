"""
Workflow definitions for OS42

Standard workflows that automate business processes
"""

from typing import Dict, Any, Optional
from datetime import datetime


# Define workflow step types
class StepType:
    """Standard step types"""
    CREATE = "create"
    REPURPOSE = "repurpose"
    DISTRIBUTE = "distribute"
    MONETIZE = "monetize"
    ANALYZE = "analyze"
    OPTIMIZE = "optimize"


class Workflow:
    """Base workflow class"""

    def __init__(self, workflow_id: str, name: str, description: str):
        self.workflow_id = workflow_id
        self.name = name
        self.description = description
        self.steps = []

    def add_step(
        self,
        engine: str,
        action: str,
        params: Dict[str, Any],
        step_id: Optional[str] = None,
        on_error: str = "stop"
    ) -> "Workflow":
        """Add a step to the workflow"""
        step = {
            "id": step_id or f"step_{len(self.steps)}",
            "engine": engine,
            "action": action,
            "params": params,
            "on_error": on_error
        }
        self.steps.append(step)
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert workflow to dictionary"""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
            "created_at": datetime.utcnow().isoformat()
        }


# ===== Content Pillar Workflow =====
def create_content_pillar_workflow(
    title: str,
    topic: str,
    content_type: str = "blog_post"
) -> Workflow:
    """
    Create a content pillar and repurpose it across channels

    Steps:
    1. Create pillar content in content-engine
    2. Repurpose into multiple formats (Twitter, LinkedIn, email)
    3. Distribute across channels via marketing-automation-engine
    4. Track monetization via revenue-operations-engine
    5. Analyze performance via analytics-engine
    """
    workflow = Workflow(
        workflow_id=f"pillar-{int(datetime.utcnow().timestamp())}",
        name="Content Pillar Creation & Distribution",
        description="Create pillar content and distribute across all channels"
    )

    # Step 1: Create pillar content
    workflow.add_step(
        engine="content",
        action="create",
        params={
            "title": title,
            "topic": topic,
            "content_type": content_type,
            "auto_publish": False
        },
        step_id="create_pillar"
    )

    # Step 2: Repurpose content
    workflow.add_step(
        engine="content",
        action="repurpose",
        params={
            "content_id": "$steps.create_pillar.id",
            "formats": ["twitter", "linkedin", "email", "newsletter"],
            "ai_model": "gpt-4"
        },
        step_id="repurpose_content"
    )

    # Step 3: Distribute to channels
    workflow.add_step(
        engine="marketing",
        action="distribute",
        params={
            "content_id": "$steps.create_pillar.id",
            "channels": ["wordpress", "dev_to", "substack"],
            "schedule": "immediate"
        },
        step_id="distribute"
    )

    # Step 4: Set up monetization
    workflow.add_step(
        engine="revenue",
        action="create_offer",
        params={
            "content_id": "$steps.create_pillar.id",
            "offer_type": "lead_magnet",
            "value_ladder": ["free", "premium", "vip"]
        },
        step_id="monetize"
    )

    # Step 5: Analyze performance
    workflow.add_step(
        engine="analytics",
        action="track",
        params={
            "content_id": "$steps.create_pillar.id",
            "metrics": ["views", "engagement", "conversions", "revenue"],
            "dashboard": "content_performance"
        },
        step_id="analyze"
    )

    return workflow


# ===== Daily Optimization Workflow =====
def create_daily_optimization_workflow() -> Workflow:
    """
    Daily optimization workflow

    Steps:
    1. Get performance data from analytics
    2. Run A/B test analysis
    3. Identify winners
    4. Adjust content strategy
    5. Generate optimization report
    """
    workflow = Workflow(
        workflow_id=f"daily-optimize-{int(datetime.utcnow().timestamp())}",
        name="Daily Optimization",
        description="Analyze performance and optimize strategy daily"
    )

    # Step 1: Collect metrics
    workflow.add_step(
        engine="analytics",
        action="get_metrics",
        params={
            "time_window": "24h",
            "metrics": ["ctr", "conversion_rate", "revenue_per_visitor"],
            "group_by": "content_type"
        },
        step_id="collect_metrics"
    )

    # Step 2: Analyze A/B tests
    workflow.add_step(
        engine="analytics",
        action="analyze_ab_tests",
        params={
            "tests": "$steps.collect_metrics.active_tests",
            "confidence_level": 0.95
        },
        step_id="analyze_tests"
    )

    # Step 3: Identify winners
    workflow.add_step(
        engine="analytics",
        action="identify_winners",
        params={
            "test_results": "$steps.analyze_tests.results",
            "min_improvement": 0.05
        },
        step_id="identify_winners"
    )

    # Step 4: Update strategy
    workflow.add_step(
        engine="content",
        action="update_strategy",
        params={
            "winning_formats": "$steps.identify_winners.formats",
            "apply_to_future": True
        },
        step_id="update_strategy"
    )

    return workflow


# ===== Audience Growth Workflow =====
def create_audience_growth_workflow() -> Workflow:
    """
    Weekly audience growth workflow

    Steps:
    1. Segment audience by engagement
    2. Create targeted nurture sequences
    3. Launch nurture campaigns
    4. Track results
    """
    workflow = Workflow(
        workflow_id=f"growth-{int(datetime.utcnow().timestamp())}",
        name="Audience Growth",
        description="Grow audience through targeted nurture campaigns"
    )

    # Step 1: Segment audience
    workflow.add_step(
        engine="marketing",
        action="segment_audience",
        params={
            "criteria": ["engagement_level", "content_preference", "lifecycle_stage"],
            "min_segment_size": 100
        },
        step_id="segment"
    )

    # Step 2: Create nurture sequences
    workflow.add_step(
        engine="marketing",
        action="create_nurture",
        params={
            "segments": "$steps.segment.segments",
            "sequence_length": 7,
            "ai_personalized": True
        },
        step_id="create_nurture"
    )

    # Step 3: Launch campaigns
    workflow.add_step(
        engine="marketing",
        action="launch_campaign",
        params={
            "nurture_sequences": "$steps.create_nurture.sequences",
            "start_immediately": True
        },
        step_id="launch"
    )

    # Step 4: Track results
    workflow.add_step(
        engine="analytics",
        action="track_campaign",
        params={
            "campaign_ids": "$steps.launch.campaign_ids",
            "track_conversions": True
        },
        step_id="track"
    )

    return workflow
