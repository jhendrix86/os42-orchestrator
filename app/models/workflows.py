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


# ===== Lead Nurture Email Workflow =====
def create_lead_nurture_email_workflow(
    lead_email: str,
    subject: str,
    from_email: str,
    lead_name: Optional[str] = None,
    campaign_name: Optional[str] = None,
    html_content: Optional[str] = None,
) -> Workflow:
    """
    Capture a lead, create a campaign to hold it under, create an email
    campaign, and send it.

    Every step below is verified against real marketing-automation-engine
    router code (2026-08-11 reconciliation, extending the Phase H pattern
    to a second engine - see CLAUDE.md at the repo root). This is the first
    workflow template in this repo whose steps live on marketing-automation-
    engine rather than content-engine.

    Real differences worth knowing:
    - POST /leads/create, POST /campaigns/create, and POST /email/create
      each persist a real database row (not mocks) - see leads.py,
      campaigns.py, email.py. campaign_type must be a real CampaignType
      enum value ("email" is one - app/models/campaign.py).
    - POST /email/{id}/send genuinely calls SendGrid per recipient
      (app/services/esp/sendgrid_client.py) and honestly reports failure
      when SENDGRID_API_KEY isn't configured - it doesn't fake success,
      same honesty contract as content-engine's distribution/execute step.
    - Leaving recipient_emails empty (this workflow's default) sends to
      every lead on file, which - since this workflow just created one -
      always includes the lead captured in step 1.
    - campaigns/{id}/launch exists but is a server-side stub ("In
      production, this would update status...") - deliberately not used
      here; launching isn't required to send an email campaign under a
      draft campaign, and calling a known stub step wouldn't be a real
      verification.
    """
    workflow = Workflow(
        workflow_id=f"nurture-{int(datetime.utcnow().timestamp())}",
        name="Lead Nurture Email",
        description="Capture a lead and send it a real email campaign",
    )

    # Step 1: Capture the lead — POST /leads/create
    workflow.add_step(
        engine="marketing",
        action="leads/create",
        params={
            "email": lead_email,
            "name": lead_name,
            "source": "orchestrator_workflow",
        },
        step_id="create_lead",
    )

    # Step 2: Create the parent campaign — POST /campaigns/create
    workflow.add_step(
        engine="marketing",
        action="campaigns/create",
        params={
            "name": campaign_name or f"Nurture - {lead_email}",
            "campaign_type": "email",
        },
        step_id="create_campaign",
    )

    # Step 3: Create the email campaign under it — POST /email/create
    workflow.add_step(
        engine="marketing",
        action="email/create",
        params={
            "campaign_id": "$steps.create_campaign.id",
            "subject": subject,
            "from_email": from_email,
            "html_content": html_content or "",
        },
        step_id="create_email_campaign",
    )

    # Step 4: Send it — POST /email/{id}/send
    workflow.add_step(
        engine="marketing",
        action="email/$steps.create_email_campaign.id/send",
        params={},
        step_id="send_email_campaign",
    )

    return workflow


# ===== Customer Subscription Workflow =====
def create_customer_subscription_workflow(
    customer_email: str,
    plan_id: str,
    payment_method_id: str,
    customer_name: Optional[str] = None,
    billing_cycle: str = "monthly",
) -> Workflow:
    """
    Create a customer, then subscribe them to a plan.

    Every step below is verified against real revenue-operations-engine
    router code (2026-08-11 reconciliation, extending the Phase H pattern
    to a third engine - see CLAUDE.md at the repo root).

    Real differences worth knowing:
    - POST /customers/ (note the trailing slash - the real route is
      registered as "/" under the "/customers" prefix; calling
      "customers" without it would hit FastAPI's 307 redirect-slash
      behavior instead of the real handler) persists a real Customer row.
    - POST /subscriptions/create does NOT write to this engine's own
      database - it's a thin, honest proxy to baselayer's income_engine
      (app/services/baselayer_client.py). Against the real engine, this
      step will report a clear "not configured" failure until a real
      baselayer service account exists (BASELAYER_SERVICE_EMAIL/PASSWORD -
      see ../HANDOFF.md's "Credentials / accounts status"), not a
      fabricated success - same honesty contract as every other real
      client in this fleet.
    - plan_id is passed straight through as baselayer's revenue stream id;
      the caller is responsible for it referring to a real stream.
    """
    workflow = Workflow(
        workflow_id=f"subscribe-{int(datetime.utcnow().timestamp())}",
        name="Customer Subscription Onboarding",
        description="Create a customer and subscribe them to a plan",
    )

    # Step 1: Create the customer — POST /customers/
    workflow.add_step(
        engine="revenue",
        action="customers/",
        params={
            "email": customer_email,
            "name": customer_name,
        },
        step_id="create_customer",
    )

    # Step 2: Subscribe them — POST /subscriptions/create
    workflow.add_step(
        engine="revenue",
        action="subscriptions/create",
        params={
            "customer_id": "$steps.create_customer.id",
            "plan_id": plan_id,
            "payment_method_id": payment_method_id,
            "billing_cycle": billing_cycle,
        },
        step_id="create_subscription",
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
