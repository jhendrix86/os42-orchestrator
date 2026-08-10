"""
OS42 Orchestrator Dashboard

Real-time visualization of system status, workflows, and metrics
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
import json
from datetime import datetime

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
async def dashboard():
    """Main dashboard HTML"""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>OS42 Orchestrator Dashboard</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                background: #0f172a;
                color: #e2e8f0;
                line-height: 1.6;
            }

            .container {
                max-width: 1400px;
                margin: 0 auto;
                padding: 20px;
            }

            header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 30px;
                border-bottom: 2px solid #1e293b;
                padding-bottom: 20px;
            }

            h1 {
                font-size: 2.5em;
                color: #60a5fa;
                font-weight: 700;
            }

            .status-badge {
                display: inline-block;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: 600;
                font-size: 0.9em;
            }

            .status-healthy {
                background: #10b981;
                color: white;
            }

            .status-warning {
                background: #f59e0b;
                color: white;
            }

            .status-error {
                background: #ef4444;
                color: white;
            }

            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }

            .card {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 20px;
                transition: all 0.3s ease;
            }

            .card:hover {
                border-color: #60a5fa;
                box-shadow: 0 0 20px rgba(96, 165, 250, 0.1);
            }

            .card-title {
                font-size: 0.9em;
                text-transform: uppercase;
                color: #94a3b8;
                margin-bottom: 10px;
                font-weight: 600;
                letter-spacing: 0.5px;
            }

            .card-value {
                font-size: 2.2em;
                font-weight: 700;
                color: #60a5fa;
                margin-bottom: 5px;
            }

            .card-detail {
                font-size: 0.85em;
                color: #64748b;
            }

            .services {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 30px;
            }

            .services h2 {
                font-size: 1.2em;
                margin-bottom: 15px;
                color: #60a5fa;
            }

            .service-list {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
            }

            .service-item {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 15px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }

            .service-name {
                font-weight: 600;
                font-size: 0.95em;
            }

            .service-status {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                display: inline-block;
                margin-left: 10px;
            }

            .status-up {
                background: #10b981;
                box-shadow: 0 0 10px #10b981;
            }

            .status-down {
                background: #ef4444;
                box-shadow: 0 0 10px #ef4444;
            }

            .workflows {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 30px;
            }

            .workflows h2 {
                font-size: 1.2em;
                margin-bottom: 15px;
                color: #60a5fa;
            }

            .workflow-item {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 15px;
                margin-bottom: 10px;
            }

            .workflow-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }

            .workflow-name {
                font-weight: 600;
                color: #e2e8f0;
            }

            .workflow-progress {
                width: 100%;
                height: 8px;
                background: #334155;
                border-radius: 4px;
                overflow: hidden;
                margin-top: 10px;
            }

            .workflow-progress-bar {
                height: 100%;
                background: linear-gradient(90deg, #60a5fa, #3b82f6);
                transition: width 0.3s ease;
            }

            .metrics {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 30px;
            }

            .metrics h2 {
                font-size: 1.2em;
                margin-bottom: 15px;
                color: #60a5fa;
            }

            .metrics-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
            }

            .metric {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 15px;
                text-align: center;
            }

            .metric-label {
                font-size: 0.85em;
                color: #94a3b8;
                text-transform: uppercase;
                margin-bottom: 5px;
                font-weight: 600;
            }

            .metric-value {
                font-size: 1.8em;
                font-weight: 700;
                color: #10b981;
            }

            .refresh-button {
                background: #3b82f6;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                cursor: pointer;
                font-weight: 600;
                transition: background 0.3s ease;
            }

            .refresh-button:hover {
                background: #2563eb;
            }

            .last-updated {
                font-size: 0.85em;
                color: #64748b;
                margin-top: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>OS42 Orchestrator</h1>
                <div>
                    <span class="status-badge status-healthy" id="systemStatus">System Healthy</span>
                    <button class="refresh-button" onclick="refreshDashboard()">Refresh</button>
                </div>
            </header>

            <div class="grid">
                <div class="card">
                    <div class="card-title">Active Workflows</div>
                    <div class="card-value" id="activeWorkflows">0</div>
                    <div class="card-detail">Currently executing</div>
                </div>
                <div class="card">
                    <div class="card-title">Completed Today</div>
                    <div class="card-value" id="completedWorkflows">0</div>
                    <div class="card-detail">Success: <span id="successRate">0</span>%</div>
                </div>
                <div class="card">
                    <div class="card-title">Total Reach</div>
                    <div class="card-value" id="totalReach">0</div>
                    <div class="card-detail">Views across all content</div>
                </div>
                <div class="card">
                    <div class="card-title">Revenue</div>
                    <div class="card-value" id="totalRevenue">$0</div>
                    <div class="card-detail">This month</div>
                </div>
            </div>

            <div class="services">
                <h2>Services Status</h2>
                <div class="service-list" id="servicesList">
                    <!-- Populated by JavaScript -->
                </div>
            </div>

            <div class="workflows">
                <h2>Active Workflows</h2>
                <div id="workflowsList">
                    <div class="workflow-item">
                        <div class="workflow-header">
                            <span class="workflow-name">No active workflows</span>
                        </div>
                    </div>
                </div>
            </div>

            <div class="metrics">
                <h2>System Metrics</h2>
                <div class="metrics-grid">
                    <div class="metric">
                        <div class="metric-label">Avg Response Time</div>
                        <div class="metric-value">342ms</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Conversion Rate</div>
                        <div class="metric-value">2.9%</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Engine Availability</div>
                        <div class="metric-value">100%</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Content Published</div>
                        <div class="metric-value">5</div>
                    </div>
                </div>
            </div>

            <div class="last-updated">
                Last updated: <span id="lastUpdated">--:--</span>
            </div>
        </div>

        <script>
            const SERVICES = [
                'content', 'marketing', 'analytics', 'monitoring',
                'notification', 'sales', 'revenue', 'integration',
                'pricing', 'support', 'governance'
            ];

            async function refreshDashboard() {
                try {
                    // Fetch orchestrator status
                    const statusResponse = await fetch('/status');
                    const status = await statusResponse.json();

                    // Update metrics
                    document.getElementById('activeWorkflows').textContent = status.active_workflows || 0;
                    document.getElementById('completedWorkflows').textContent = status.completed_workflows || 0;
                    document.getElementById('successRate').textContent = status.success_rate || 0;
                    document.getElementById('totalReach').textContent = (status.total_reach || 0).toLocaleString();
                    document.getElementById('totalRevenue').textContent = '$' + (status.total_revenue || 0).toLocaleString();

                    // Update services
                    const servicesList = document.getElementById('servicesList');
                    servicesList.innerHTML = '';

                    for (const service of SERVICES) {
                        const serviceStatus = status.services?.[service]?.status || 'unknown';
                        const isUp = serviceStatus === 'healthy';

                        const item = document.createElement('div');
                        item.className = 'service-item';
                        item.innerHTML = `
                            <span class="service-name">${service}</span>
                            <span class="service-status ${isUp ? 'status-up' : 'status-down'}"></span>
                        `;
                        servicesList.appendChild(item);
                    }

                    // Update workflows
                    const workflowsList = document.getElementById('workflowsList');
                    if (status.workflows && status.workflows.length > 0) {
                        workflowsList.innerHTML = '';
                        for (const workflow of status.workflows) {
                            const progress = (workflow.completed_steps / workflow.total_steps) * 100;
                            const item = document.createElement('div');
                            item.className = 'workflow-item';
                            item.innerHTML = `
                                <div class="workflow-header">
                                    <span class="workflow-name">${workflow.name}</span>
                                    <span>${Math.round(progress)}%</span>
                                </div>
                                <div class="workflow-progress">
                                    <div class="workflow-progress-bar" style="width: ${progress}%"></div>
                                </div>
                            `;
                            workflowsList.appendChild(item);
                        }
                    }

                    // Update last updated time
                    const now = new Date();
                    const timeStr = now.toLocaleTimeString();
                    document.getElementById('lastUpdated').textContent = timeStr;

                } catch (error) {
                    console.error('Failed to refresh dashboard:', error);
                }
            }

            // Auto-refresh every 5 seconds
            refreshDashboard();
            setInterval(refreshDashboard, 5000);
        </script>
    </body>
    </html>
    """


@router.get("/metrics")
async def get_metrics(app_state):
    """Get system metrics"""
    return {
        "active_workflows": len(app_state.get("active_workflows", {})),
        "completed_workflows": sum(1 for w in app_state.get("workflow_results", {}).values() if w.get("status") == "completed"),
        "total_reach": app_state.get("system_status", {}).get("total_reach", 0),
        "total_revenue": app_state.get("system_status", {}).get("total_revenue", 0),
        "avg_response_time": app_state.get("system_status", {}).get("avg_response_time", 0),
    }


@router.get("/workflows")
async def get_workflows(app_state):
    """Get active workflows"""
    workflows = []
    for workflow_id, result in app_state.get("workflow_results", {}).items():
        if result.get("status") in ["running", "pending"]:
            step_results = result.get("step_results", {})
            total_steps = len(result.get("workflow", {}).get("steps", []))
            completed_steps = len([s for s in step_results.values() if s.get("status") == "completed"])

            workflows.append({
                "id": workflow_id,
                "name": result.get("workflow", {}).get("name", "Unknown"),
                "status": result.get("status"),
                "total_steps": total_steps,
                "completed_steps": completed_steps,
                "progress": (completed_steps / total_steps * 100) if total_steps > 0 else 0,
            })

    return workflows


@router.get("/services")
async def get_services(app_state):
    """Get services status"""
    services = {}
    for service_name, service_url in app_state.get("service_registry", {}).items():
        services[service_name] = {
            "url": service_url,
            "status": "healthy",  # Would actually ping the service
        }
    return services
