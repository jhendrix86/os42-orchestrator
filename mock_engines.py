#!/usr/bin/env python3
"""
Mock engines for OS42 Orchestrator - local dev/demo only

A single stand-in HTTP service that answers every action the orchestrator
calls: workflow DSL steps (content/create, marketing/distribute, ...) and
DecisionExecutor's engine-owned actions (marketing/scale_budget, ...).
None of the 11 sibling engine repos implement a real contract yet (every
phase's tech debt notes flag this) - this lets the orchestrator actually
run against something that answers, end to end, without needing any of
those repos to exist yet.

Run it, then point the orchestrator at it (see PHASE_F_COMPLETION.md for
the full walkthrough):
    python mock_engines.py                    # starts on :9000
    $env:CONTENT_ENGINE_URL = "http://localhost:9000"
    $env:MARKETING_ENGINE_URL = "http://localhost:9000"
    ... (repeat for every *_ENGINE_URL, or just point them all at :9000)
    python -m app.main
"""

import os
import uuid
from datetime import datetime

from fastapi import FastAPI, Request

app = FastAPI(title="OS42 Mock Engines", description="Reference stand-in for every sibling engine")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "mock-engines"}


@app.post("/{action:path}")
async def handle_any_action(action: str, request: Request):
    """
    Answers any action any engine might be asked for with a generic,
    canned success response. Real engines will have real, differentiated
    contracts; this exists to prove the orchestrator's HTTP mechanics
    (parameter resolution, on_error handling, decision application) work
    when something is actually listening, not to simulate real business
    logic.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    record_id = f"mock-{uuid.uuid4().hex[:8]}"

    return {
        "status": "ok",
        "action": action,
        "id": record_id,
        "received": payload,
        "handled_at": datetime.utcnow().isoformat(),
        # Generic fields some workflow steps pull via $steps.x.y - harmless
        # if a given action doesn't use them.
        "formats": {"twitter": ["mock tweet"], "linkedin": "mock post"},
        "distribution_results": {
            "wordpress": {"status": "published", "url": f"https://example.com/{record_id}"}
        },
        "reach": 1000,
        "offer_id": record_id,
        "tracking_id": record_id,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("MOCK_ENGINES_PORT", "9000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
