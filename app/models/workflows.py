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


# ===== Support Escalation Workflow =====
def create_support_escalation_workflow(
    customer_name: str,
    customer_email: str,
    subject: str,
    message: str,
    notify_recipient: str,
    priority: str = "high",
    notify_channel: str = "email",
) -> Workflow:
    """
    File a support ticket, escalate it, and notify the on-call recipient.

    Every step below is verified against real customer-support-engine and
    notification-engine router code (Step 9, 2026-08-30 reconciliation -
    extending the Phase H/I pattern to the two engines Stage 4's rollout
    made genuinely real: see ../HANDOFF.md's 2026-08-12/15 "6 remaining
    mock engines made real" entry and Nexus's 2026-08-29 stale-image audit,
    which is what makes this the first session that could actually trust
    these two engines' source as reflecting what's deployed).

    Real differences worth knowing:
    - POST /tickets/create persists a real Ticket row (and a real Customer
      row, get-or-created by email) - see tickets.py's own docstring,
      "real DB-backed CRUD against the tickets table."
    - POST /tickets/{id}/escalate only flips ticket.status to ESCALATED;
      it does not itself notify anyone - that's genuinely a separate real
      step, not a formality, which is why this workflow's third step exists.
    - POST /notifications/send genuinely attempts delivery on the first
      requested channel via app/services/delivery/dispatch.py and reports
      an honest per-channel success/failure - it does not fake delivery.
    - priority must be a real TicketPriority enum value (customer-support-
      engine's app/models/ticket.py: critical/high/medium/low) -
      "critical" tickets get the tightest real SLA deadline.
    """
    workflow = Workflow(
        workflow_id=f"escalation-{int(datetime.utcnow().timestamp())}",
        name="Support Escalation Notification",
        description="File a support ticket, escalate it, and notify on-call",
    )

    # Step 1: File the ticket — POST /tickets/create
    workflow.add_step(
        engine="support",
        action="tickets/create",
        params={
            "customer_name": customer_name,
            "customer_email": customer_email,
            "subject": subject,
            "message": message,
            "priority": priority,
        },
        step_id="create_ticket",
    )

    # Step 2: Escalate it — POST /tickets/{id}/escalate
    workflow.add_step(
        engine="support",
        action="tickets/$steps.create_ticket.id/escalate",
        params={},
        step_id="escalate_ticket",
    )

    # Step 3: Notify on-call — POST /notifications/send
    workflow.add_step(
        engine="notification",
        action="notifications/send",
        params={
            "recipient": notify_recipient,
            "recipient_type": "email",
            "channels": [notify_channel],
            "subject": f"Escalated: {subject}",
            "message": f"Ticket $steps.create_ticket.id escalated for {customer_email}: {message}",
        },
        step_id="notify_oncall",
    )

    return workflow


# ===== Integration Sync Workflow =====
def create_integration_sync_workflow(
    name: str,
    provider: str,
    sync_url: str,
    integration_type: str = "custom",
) -> Workflow:
    """
    Register an integration, then trigger a real sync run against it.

    Verified against real integration-engine router code (Step 9,
    2026-08-30 reconciliation).

    Real differences worth knowing:
    - POST /integrations/create persists a real Integration row (and a
      real, encrypted Credential row if credentials are supplied) - see
      integrations.py's own docstring, "real DB-backed CRUD against the
      integrations table."
    - POST /integrations/{id}/sync creates a real SyncJob row and runs it
      via app/services/sync_engine.py, which makes a genuine outbound HTTP
      call to the integration's own config["sync_url"] - there's no
      per-vendor SDK for any provider this schema anticipates, so "real"
      here means a real HTTP call to whatever endpoint was configured, not
      a simulated one. It honestly fails ("no 'sync_url' configured") if
      config carries none, rather than fabricating a progress number -
      this workflow always supplies one for exactly that reason.
    - integration_type must be a real IntegrationType enum value
      (integration-engine's app/models/integration.py) - "custom" always
      exists; "crm"/"marketing"/"analytics"/"productivity" are also real.
    """
    workflow = Workflow(
        workflow_id=f"intsync-{int(datetime.utcnow().timestamp())}",
        name="Integration Sync",
        description="Register an integration and run a real sync against it",
    )

    # Step 1: Register the integration — POST /integrations/create
    workflow.add_step(
        engine="integration",
        action="integrations/create",
        params={
            "name": name,
            "integration_type": integration_type,
            "provider": provider,
            "config": {"sync_url": sync_url},
        },
        step_id="create_integration",
    )

    # Step 2: Trigger a real sync — POST /integrations/{id}/sync
    workflow.add_step(
        engine="integration",
        action="integrations/$steps.create_integration.id/sync",
        params={},
        step_id="trigger_sync",
    )

    return workflow


# ===== Analytics Report Workflow =====
def create_analytics_report_workflow(
    report_name: str,
    metric_names: Optional[list] = None,
    period_days: int = 30,
) -> Workflow:
    """
    Create an analytics report, then generate it.

    Verified against real analytics-engine router code (Step 9, 2026-08-30
    reconciliation).

    Real differences worth knowing:
    - POST /reports/ (note the trailing slash - the real route is
      registered as "/" under the "/reports" prefix, same
      redirect-on-missing-slash gotcha as revenue-operations-engine's
      /customers/ - calling "reports" without it would hit FastAPI's 307
      redirect instead of the real handler) persists a real Report row
      with status PENDING.
    - POST /reports/{id}/generate computes a real aggregate over
      actually-recorded Metric rows for the requested metric_names/
      period_days - see reports.py's own docstring. It does not claim a
      PDF/CSV exists at a fake output_url; no file-generation
      infrastructure exists in this engine, so the honestly computable
      output (real numbers) is stored in extra_metadata instead. Against
      the real engine, an empty metric_names list or a period with no
      recorded metrics yields a real report with zero/empty results, not
      a failure - this step reports failure only on an actual error.
    """
    workflow = Workflow(
        workflow_id=f"report-{int(datetime.utcnow().timestamp())}",
        name="Analytics Report Generation",
        description="Create an analytics report and generate it",
    )

    # Step 1: Create the report — POST /reports/
    workflow.add_step(
        engine="analytics",
        action="reports/",
        params={
            "name": report_name,
            "report_type": "metrics_summary",
            "metric_names": metric_names or [],
            "period_days": period_days,
        },
        step_id="create_report",
    )

    # Step 2: Generate it — POST /reports/{id}/generate
    workflow.add_step(
        engine="analytics",
        action="reports/$steps.create_report.id/generate",
        params={},
        step_id="generate_report",
    )

    return workflow


# ===== Lead Conversion Workflow =====
def create_lead_conversion_workflow(
    lead_name: str,
    lead_email: str,
    estimated_value: Optional[int] = None,
    deal_name: Optional[str] = None,
) -> Workflow:
    """
    Capture a sales lead, then convert it into a real pipeline deal.

    Verified against real sales-engine router code (Step 9, 2026-08-30
    reconciliation).

    Real differences worth knowing:
    - POST /leads/create persists a real Lead row - see leads.py's own
      docstring, "real DB-backed CRUD against the leads table."
    - POST /leads/{id}/convert creates a real Deal row in the pipeline
      (app/models/pipeline.py) and updates the lead's own status/
      pipeline_stage to reflect it - it's a genuine state transition, not
      a label change. deal_name/stage_id are both optional; the endpoint
      picks a sensible default (the lead's name, and the pipeline's first
      real stage) when omitted.
    """
    workflow = Workflow(
        workflow_id=f"convert-{int(datetime.utcnow().timestamp())}",
        name="Lead Conversion",
        description="Capture a lead and convert it into a pipeline deal",
    )

    # Step 1: Capture the lead — POST /leads/create
    workflow.add_step(
        engine="sales",
        action="leads/create",
        params={
            "name": lead_name,
            "email": lead_email,
            "estimated_value": estimated_value,
        },
        step_id="create_lead",
    )

    # Step 2: Convert it — POST /leads/{id}/convert
    workflow.add_step(
        engine="sales",
        action="leads/$steps.create_lead.id/convert",
        params={"deal_name": deal_name} if deal_name else {},
        step_id="convert_lead",
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
