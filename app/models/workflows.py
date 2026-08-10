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
    Create a content pillar, repurpose it, and distribute it to a platform.

    Every step below is verified against real content-engine router code
    (2026-08-10 reconciliation - see CLAUDE.md at the repo root). The
    original version of this workflow called five invented actions
    (content/create, content/repurpose, marketing/distribute,
    revenue/create_offer, analytics/track) that never existed as real
    routes anywhere in the fleet - none of it had ever actually run
    against a real engine before this.

    Real differences worth knowing:
    - Distribution and content performance tracking both live on
      content-engine itself, not marketing-automation-engine/
      analytics-engine like the original version assumed.
    - Distribution is genuinely two steps in the real API (record, then
      execute) - content-engine's /distribution/{id}/execute reports an
      honest failure if the target platform has no configured credentials,
      it doesn't fake success.
    - There is no monetization/"offer creation" endpoint anywhere in the
      fleet - revenue-operations-engine is a real Stripe-backed billing/
      subscription/invoicing system with no concept of "offers." The
      monetize step from the original version is dropped rather than
      pointed at something invented; add it back once/if that capability
      exists somewhere real.
    """
    workflow = Workflow(
        workflow_id=f"pillar-{int(datetime.utcnow().timestamp())}",
        name="Content Pillar Creation & Distribution",
        description="Create pillar content, repurpose it, and distribute it to a platform"
    )

    # Step 1: Generate pillar content — POST /content/generate
    workflow.add_step(
        engine="content",
        action="content/generate",
        params={
            "title": title,
            "topic": topic,
            "content_type": content_type,
        },
        step_id="create_pillar"
    )

    # Step 2: Repurpose into other formats — POST /content/{id}/repurpose
    workflow.add_step(
        engine="content",
        action="content/$steps.create_pillar.id/repurpose",
        params={
            "target_types": ["social_media", "email_copy"],
        },
        step_id="repurpose_content"
    )

    # Step 3: Record a distribution request — POST /distribution/publish
    workflow.add_step(
        engine="content",
        action="distribution/publish",
        params={
            "content_id": "$steps.create_pillar.id",
            "platform": "wordpress",
        },
        step_id="record_distribution"
    )

    # Step 4: Actually attempt the publish — POST /distribution/{id}/execute
    workflow.add_step(
        engine="content",
        action="distribution/$steps.record_distribution.id/execute",
        params={},
        step_id="execute_distribution"
    )

    # Step 5: Initialize performance tracking — POST /analytics/content/{id}/track
    workflow.add_step(
        engine="content",
        action="analytics/$steps.create_pillar.id/track",
        params={
            "views": 0,
            "engagements": 0,
            "conversions": 0,
        },
        step_id="track"
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

    UNVERIFIED (2026-08-10 reconciliation - see CLAUDE.md): unlike
    create_content_pillar_workflow, this template was never remapped to
    real endpoints. This function is also never called anywhere in this
    repo (confirmed by search) - it's aspirational, not exercised by any
    test.

    Follow-up check (same day, continued reconciliation): confirmed there
    genuinely isn't a meaningful real remapping available, not just an
    unverified one. analytics-engine's real routers were read directly:
    GET /metrics/real-time and GET /metrics/historical exist and are
    real, callable paths, but their own server-side implementation is a
    hardcoded mock ("In production, this would query from database... For
    now, return a mock response" - literally in the source). None of
    analytics-engine's other routers (dashboards, kpi, predictions,
    reports - all generic list/create/get-by-id CRUD) offer anything
    resembling "identify winners" or "update strategy" either. Real A/B
    winner reporting exists, but only folded into
    GET /email/{id}/ab-results on marketing-automation-engine (requires an
    existing email campaign ID - not a generic "analyze these tests"
    action). Rebuilding this workflow around the one real-but-mocked
    metrics endpoint, dropping the other 4/5 of its steps, would
    misrepresent it more than leaving it flagged - left as-is.
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

    UNVERIFIED (2026-08-10 reconciliation - see CLAUDE.md): never remapped
    to real endpoints, never called anywhere in this repo (confirmed by
    search). A fleet-wide check found marketing-automation-engine has real
    POST /segments/create (creating a segment) but no "segment_audience"
    action; no create_nurture endpoint anywhere. POST /campaigns/create and
    POST /campaigns/{id}/launch are real and callable (see
    create_content_pillar_workflow's remapping pattern for how to do this
    properly) but launch_campaign's own server-side implementation is
    itself still a stub ("In production, this would update status..." -
    see marketing-automation-engine/app/routers/campaigns.py). No
    track_campaign endpoint exists.

    Follow-up check (same day, continued reconciliation): re-verified
    segments.py/leads.py directly, confirming the above - segments.py has
    only create/get-by-id/list (no engagement-based segmenting action),
    leads.py adds GET /{lead_id}/score but nothing resembling nurture
    sequences. Only 1 of 4 steps (launch_campaign) has any real target at
    all, and that target is itself a stub - rebuilding around it would
    misrepresent this workflow more than leaving it flagged. Left as-is.
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
