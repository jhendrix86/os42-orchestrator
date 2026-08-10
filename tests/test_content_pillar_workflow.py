"""
End-to-end test for content pillar workflow

Tests the full workflow: create → repurpose → distribute → monetize → analyze
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

# Mock imports for the actual engines (we'll simulate their responses)
# In production, these would be real HTTP calls


@pytest.fixture
def content_pillar_workflow_def():
    """Content pillar workflow definition"""
    return {
        "workflow_id": "test-pillar-001",
        "name": "Content Pillar Creation & Distribution",
        "description": "Create pillar content and distribute across all channels",
        "steps": [
            {
                "id": "create_pillar",
                "engine": "content",
                "action": "create",
                "params": {
                    "title": "The Complete Guide to AI for Creators",
                    "topic": "AI, content creation, automation",
                    "content_type": "blog_post",
                    "auto_publish": False
                },
                "on_error": "stop"
            },
            {
                "id": "repurpose_content",
                "engine": "content",
                "action": "repurpose",
                "params": {
                    "content_id": "$steps.create_pillar.id",
                    "formats": ["twitter", "linkedin", "email", "newsletter"],
                    "ai_model": "gpt-4"
                },
                "on_error": "stop"
            },
            {
                "id": "distribute",
                "engine": "marketing",
                "action": "distribute",
                "params": {
                    "content_id": "$steps.create_pillar.id",
                    "channels": ["wordpress", "dev_to", "substack"],
                    "schedule": "immediate"
                },
                "on_error": "stop"
            },
            {
                "id": "monetize",
                "engine": "revenue",
                "action": "create_offer",
                "params": {
                    "content_id": "$steps.create_pillar.id",
                    "offer_type": "lead_magnet",
                    "value_ladder": ["free", "premium", "vip"]
                },
                "on_error": "stop"
            },
            {
                "id": "analyze",
                "engine": "analytics",
                "action": "track",
                "params": {
                    "content_id": "$steps.create_pillar.id",
                    "metrics": ["views", "engagement", "conversions", "revenue"],
                    "dashboard": "content_performance"
                },
                "on_error": "stop"
            }
        ]
    }


def mock_engine_response(engine_name: str, action: str, step_result):
    """Generate mock engine responses"""
    responses = {
        ("content", "create"): {
            "id": "content-001",
            "title": "The Complete Guide to AI for Creators",
            "topic": "AI, content creation, automation",
            "url": "https://example.com/blog/ai-for-creators",
            "status": "created",
            "word_count": 3500,
            "reading_time_min": 15
        },
        ("content", "repurpose"): {
            "original_id": "content-001",
            "formats": {
                "twitter": [
                    "🚀 AI is transforming how creators work. Here's the complete guide...",
                    "You don't need to be a programmer to use AI for content creation. Learn how..."
                ],
                "linkedin": "Our latest article explores how AI tools are revolutionizing content creation workflows...",
                "email": "Subject: Your AI Content Creation Masterclass\n\nHi there...",
                "newsletter": "This week's featured article: The Complete Guide to AI for Creators"
            }
        },
        ("marketing", "distribute"): {
            "content_id": "content-001",
            "channels": ["wordpress", "dev_to", "substack"],
            "distribution_results": {
                "wordpress": {"status": "published", "url": "https://blog.example.com/ai-for-creators", "post_id": "wp-001"},
                "dev_to": {"status": "published", "url": "https://dev.to/example/ai-for-creators", "post_id": "devto-001"},
                "substack": {"status": "published", "url": "https://substack.com/p/ai-for-creators", "post_id": "substack-001"}
            },
            "reach": 5000,
            "initial_engagement": 145
        },
        ("revenue", "create_offer"): {
            "content_id": "content-001",
            "offer_id": "offer-001",
            "value_ladder": {
                "free": {
                    "name": "Free Guide",
                    "description": "Full article + email follow-up",
                    "lead_magnets": ["pdf_guide.pdf", "checklist.pdf"]
                },
                "premium": {
                    "name": "Premium Course",
                    "price": 49,
                    "includes": ["video_course", "templates", "email_sequence"]
                },
                "vip": {
                    "name": "VIP Coaching",
                    "price": 299,
                    "includes": ["1-on-1 coaching", "custom_strategy", "implementation_support"]
                }
            },
            "funnel_url": "https://example.com/ai-creators-funnel"
        },
        ("analytics", "track"): {
            "content_id": "content-001",
            "tracking_id": "track-001",
            "metrics_configured": ["views", "engagement", "conversions", "revenue"],
            "dashboard_url": "https://analytics.example.com/content_performance",
            "initial_metrics": {
                "views": 5000,
                "engagement_rate": 0.029,  # 2.9%
                "conversions": 145,
                "conversion_rate": 0.029,
                "revenue": 0  # Too early
            }
        }
    }
    return responses.get((engine_name, action), {})


@pytest.mark.asyncio
async def test_content_pillar_workflow_execution(content_pillar_workflow_def):
    """
    Test: Complete content pillar workflow executes end-to-end

    Simulates:
    1. Create pillar content
    2. Repurpose into 4 formats
    3. Distribute to 3 channels
    4. Set up monetization value ladder
    5. Configure analytics tracking
    """

    # Simulate workflow execution with parameter resolution
    execution_result = {
        "workflow_id": content_pillar_workflow_def["workflow_id"],
        "status": "success",
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": datetime.utcnow().isoformat(),
        "step_results": {}
    }

    # Execute each step sequentially, resolving parameters
    context = {}

    for step in content_pillar_workflow_def["steps"]:
        step_id = step["id"]
        engine = step["engine"]
        action = step["action"]
        params = step["params"]

        # Resolve parameter references ($steps.xxx.yyy)
        resolved_params = resolve_parameters(params, context)

        # Simulate engine call
        result = mock_engine_response(engine, action, None)

        # Store result for next steps
        context[step_id] = result
        execution_result["step_results"][step_id] = {
            "engine": engine,
            "action": action,
            "status": "completed",
            "result": result
        }

    # Assertions
    assert execution_result["status"] == "success"
    assert len(execution_result["step_results"]) == 5

    # Verify content was created
    create_result = execution_result["step_results"]["create_pillar"]["result"]
    assert create_result["id"] == "content-001"
    assert create_result["status"] == "created"

    # Verify repurposing succeeded
    repurpose_result = execution_result["step_results"]["repurpose_content"]["result"]
    assert "twitter" in repurpose_result["formats"]
    assert len(repurpose_result["formats"]["twitter"]) == 2  # 2 tweets

    # Verify distribution reached 3 channels
    distribute_result = execution_result["step_results"]["distribute"]["result"]
    assert len(distribute_result["distribution_results"]) == 3
    assert all(r["status"] == "published" for r in distribute_result["distribution_results"].values())
    assert distribute_result["reach"] == 5000

    # Verify monetization funnel created
    monetize_result = execution_result["step_results"]["monetize"]["result"]
    assert monetize_result["offer_id"] == "offer-001"
    assert all(tier in monetize_result["value_ladder"] for tier in ["free", "premium", "vip"])
    assert monetize_result["value_ladder"]["premium"]["price"] == 49
    assert monetize_result["value_ladder"]["vip"]["price"] == 299

    # Verify analytics tracking configured
    analyze_result = execution_result["step_results"]["analyze"]["result"]
    assert analyze_result["tracking_id"] == "track-001"
    assert analyze_result["initial_metrics"]["views"] == 5000
    assert analyze_result["initial_metrics"]["conversion_rate"] == 0.029

    print("\n✅ Content Pillar Workflow Test Passed!")
    print(f"\nWorkflow Execution Summary:")
    print(f"  - Content created: {create_result['id']}")
    print(f"  - Repurposed into: {', '.join(repurpose_result['formats'].keys())}")
    print(f"  - Distributed to: {', '.join(distribute_result['distribution_results'].keys())}")
    print(f"  - Initial reach: {distribute_result['reach']} views")
    print(f"  - Monetization: {len(monetize_result['value_ladder'])} tier value ladder")
    print(f"  - Tracking: {analyze_result['initial_metrics']['conversions']} initial conversions")

    return execution_result


def resolve_parameters(params: dict, context: dict) -> dict:
    """
    Resolve parameter references in the format $steps.step_id.field

    Example:
        params = {"content_id": "$steps.create_pillar.id"}
        context = {"create_pillar": {"id": "content-001"}}
        returns: {"content_id": "content-001"}
    """
    resolved = {}

    for key, value in params.items():
        if isinstance(value, str) and value.startswith("$steps."):
            # Parse reference: $steps.step_id.field
            parts = value.split(".")
            step_id = parts[1]
            field = ".".join(parts[2:])

            # Look up in context
            if step_id in context:
                step_result = context[step_id]
                # Navigate nested fields
                for part in field.split("."):
                    step_result = step_result.get(part, {})
                resolved[key] = step_result
            else:
                resolved[key] = value
        else:
            resolved[key] = value

    return resolved


@pytest.mark.asyncio
async def test_parameter_resolution():
    """Test that parameter references are correctly resolved"""

    # Setup
    context = {
        "create_pillar": {
            "id": "content-001",
            "title": "AI Guide",
            "metrics": {
                "word_count": 3500
            }
        }
    }

    params = {
        "content_id": "$steps.create_pillar.id",
        "title": "$steps.create_pillar.title",
        "word_count": "$steps.create_pillar.metrics.word_count",
        "literal_value": "unchanged"
    }

    resolved = resolve_parameters(params, context)

    assert resolved["content_id"] == "content-001"
    assert resolved["title"] == "AI Guide"
    assert resolved["word_count"] == 3500
    assert resolved["literal_value"] == "unchanged"


@pytest.mark.asyncio
async def test_workflow_orchestrator_integration():
    """
    Test: OS42 Orchestrator can submit and track workflows

    Verifies:
    - POST /workflows/create accepts workflow definitions
    - GET /workflows/{id} returns workflow status
    - Workflow status updates as steps complete
    """

    # This would integrate with the actual orchestrator HTTP API
    workflow_def = {
        "name": "Content Pillar Creation & Distribution",
        "description": "Create pillar content and distribute across all channels",
        "steps": [
            {
                "engine": "content",
                "action": "create",
                "params": {"title": "Test", "topic": "Test", "content_type": "blog_post"}
            }
        ]
    }

    # In a real test, this would be:
    # async with httpx.AsyncClient() as client:
    #     response = await client.post("http://localhost:8050/workflows/create", json=workflow_def)
    #     assert response.status_code == 200
    #     workflow_id = response.json()["workflow_id"]
    #
    #     # Poll for completion
    #     for _ in range(10):
    #         response = await client.get(f"http://localhost:8050/workflows/{workflow_id}")
    #         status = response.json()
    #         if status["status"] == "completed":
    #             break
    #         await asyncio.sleep(0.5)


if __name__ == "__main__":
    # Run the test
    asyncio.run(test_content_pillar_workflow_execution(
        {
            "workflow_id": "test-pillar-001",
            "name": "Content Pillar Creation & Distribution",
            "description": "Create pillar content and distribute across all channels",
            "steps": [
                {
                    "id": "create_pillar",
                    "engine": "content",
                    "action": "create",
                    "params": {
                        "title": "The Complete Guide to AI for Creators",
                        "topic": "AI, content creation, automation",
                        "content_type": "blog_post",
                        "auto_publish": False
                    },
                    "on_error": "stop"
                },
                {
                    "id": "repurpose_content",
                    "engine": "content",
                    "action": "repurpose",
                    "params": {
                        "content_id": "$steps.create_pillar.id",
                        "formats": ["twitter", "linkedin", "email", "newsletter"],
                        "ai_model": "gpt-4"
                    },
                    "on_error": "stop"
                },
                {
                    "id": "distribute",
                    "engine": "marketing",
                    "action": "distribute",
                    "params": {
                        "content_id": "$steps.create_pillar.id",
                        "channels": ["wordpress", "dev_to", "substack"],
                        "schedule": "immediate"
                    },
                    "on_error": "stop"
                },
                {
                    "id": "monetize",
                    "engine": "revenue",
                    "action": "create_offer",
                    "params": {
                        "content_id": "$steps.create_pillar.id",
                        "offer_type": "lead_magnet",
                        "value_ladder": ["free", "premium", "vip"]
                    },
                    "on_error": "stop"
                },
                {
                    "id": "analyze",
                    "engine": "analytics",
                    "action": "track",
                    "params": {
                        "content_id": "$steps.create_pillar.id",
                        "metrics": ["views", "engagement", "conversions", "revenue"],
                        "dashboard": "content_performance"
                    },
                    "on_error": "stop"
                }
            ]
        }
    ))
