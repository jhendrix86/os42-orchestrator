"""
Metrics aggregation and performance analysis for OS42

Collects metrics from all engines, analyzes performance, recommends optimizations
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json


class MetricType(str, Enum):
    """Types of metrics collected from engines"""
    VIEWS = "views"
    CLICKS = "clicks"
    CONVERSIONS = "conversions"
    REVENUE = "revenue"
    ENGAGEMENT = "engagement"
    RESPONSE_TIME = "response_time"
    ERROR_RATE = "error_rate"
    COMPLETION_RATE = "completion_rate"


class OptimizationAction(str, Enum):
    """Actions the system can take to optimize"""
    INCREASE_FREQUENCY = "increase_frequency"
    DECREASE_FREQUENCY = "decrease_frequency"
    CHANGE_FORMAT = "change_format"
    CHANGE_CHANNEL = "change_channel"
    ADJUST_TIMING = "adjust_timing"
    SCALE_BUDGET = "scale_budget"
    PAUSE = "pause"
    RESUME = "resume"


@dataclass
class MetricPoint:
    """Single metric data point"""
    timestamp: datetime
    metric_type: MetricType
    value: float
    engine: str
    workflow_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "timestamp": self.timestamp.isoformat(),
            "metric_type": self.metric_type,
            "value": self.value,
            "engine": self.engine,
            "workflow_id": self.workflow_id,
            "context": self.context
        }


@dataclass
class PerformanceAnalysis:
    """Analysis of performance over time"""
    workflow_id: str
    period_start: datetime
    period_end: datetime
    metrics: Dict[MetricType, List[float]]

    # Computed metrics
    conversion_rate: Optional[float] = None
    engagement_rate: Optional[float] = None
    revenue_per_conversion: Optional[float] = None
    avg_response_time: Optional[float] = None
    error_rate: Optional[float] = None
    completion_rate: Optional[float] = None

    # Trends
    conversion_trend: Optional[str] = None  # "improving", "declining", "stable"
    revenue_trend: Optional[str] = None

    # Recommendations
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "workflow_id": self.workflow_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "conversion_rate": self.conversion_rate,
            "engagement_rate": self.engagement_rate,
            "revenue_per_conversion": self.revenue_per_conversion,
            "avg_response_time": self.avg_response_time,
            "error_rate": self.error_rate,
            "completion_rate": self.completion_rate,
            "conversion_trend": self.conversion_trend,
            "revenue_trend": self.revenue_trend,
            "recommendations": self.recommendations
        }


class MetricsAggregator:
    """Collects and aggregates metrics from all engines"""

    def __init__(self):
        self.metrics: List[MetricPoint] = []
        self.workflow_metrics: Dict[str, List[MetricPoint]] = {}

    def add_metric(self, metric: MetricPoint):
        """Add a metric point"""
        self.metrics.append(metric)

        if metric.workflow_id:
            if metric.workflow_id not in self.workflow_metrics:
                self.workflow_metrics[metric.workflow_id] = []
            self.workflow_metrics[metric.workflow_id].append(metric)

    def get_metrics(self, workflow_id: str, metric_type: Optional[MetricType] = None,
                   start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None) -> List[MetricPoint]:
        """Get metrics for a workflow"""
        if workflow_id not in self.workflow_metrics:
            return []

        metrics = self.workflow_metrics[workflow_id]

        # Filter by metric type
        if metric_type:
            metrics = [m for m in metrics if m.metric_type == metric_type]

        # Filter by time range
        if start_time:
            metrics = [m for m in metrics if m.timestamp >= start_time]
        if end_time:
            metrics = [m for m in metrics if m.timestamp <= end_time]

        return metrics

    def compute_conversion_rate(self, workflow_id: str, period_hours: int = 24) -> Optional[float]:
        """Compute conversion rate over period"""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=period_hours)

        conversions = self.get_metrics(workflow_id, MetricType.CONVERSIONS, start_time, end_time)
        views = self.get_metrics(workflow_id, MetricType.VIEWS, start_time, end_time)

        if not views:
            return None

        total_views = sum(m.value for m in views)
        total_conversions = sum(m.value for m in conversions)

        if total_views == 0:
            return None

        return total_conversions / total_views

    def compute_revenue_per_conversion(self, workflow_id: str, period_hours: int = 24) -> Optional[float]:
        """Compute revenue per conversion"""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=period_hours)

        conversions = self.get_metrics(workflow_id, MetricType.CONVERSIONS, start_time, end_time)
        revenue = self.get_metrics(workflow_id, MetricType.REVENUE, start_time, end_time)

        if not conversions:
            return None

        total_conversions = sum(m.value for m in conversions)
        total_revenue = sum(m.value for m in revenue)

        if total_conversions == 0:
            return None

        return total_revenue / total_conversions

    def compute_engagement_rate(self, workflow_id: str, period_hours: int = 24) -> Optional[float]:
        """Compute engagement rate (clicks/views)"""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=period_hours)

        clicks = self.get_metrics(workflow_id, MetricType.CLICKS, start_time, end_time)
        views = self.get_metrics(workflow_id, MetricType.VIEWS, start_time, end_time)

        if not views:
            return None

        total_views = sum(m.value for m in views)
        total_clicks = sum(m.value for m in clicks)

        if total_views == 0:
            return None

        return total_clicks / total_views

    def analyze_performance(self, workflow_id: str, period_hours: int = 24) -> PerformanceAnalysis:
        """Analyze workflow performance over period"""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=period_hours)

        # Collect all metric types
        metrics_by_type: Dict[MetricType, List[float]] = {}
        for metric_type in MetricType:
            points = self.get_metrics(workflow_id, metric_type, start_time, end_time)
            metrics_by_type[metric_type] = [m.value for m in points]

        # Create analysis
        analysis = PerformanceAnalysis(
            workflow_id=workflow_id,
            period_start=start_time,
            period_end=end_time,
            metrics=metrics_by_type
        )

        # Compute derived metrics
        analysis.conversion_rate = self.compute_conversion_rate(workflow_id, period_hours)
        analysis.revenue_per_conversion = self.compute_revenue_per_conversion(workflow_id, period_hours)
        analysis.engagement_rate = self.compute_engagement_rate(workflow_id, period_hours)

        if metrics_by_type.get(MetricType.RESPONSE_TIME):
            analysis.avg_response_time = sum(metrics_by_type[MetricType.RESPONSE_TIME]) / len(metrics_by_type[MetricType.RESPONSE_TIME])

        if metrics_by_type.get(MetricType.ERROR_RATE):
            analysis.error_rate = sum(metrics_by_type[MetricType.ERROR_RATE]) / len(metrics_by_type[MetricType.ERROR_RATE])

        if metrics_by_type.get(MetricType.COMPLETION_RATE):
            analysis.completion_rate = sum(metrics_by_type[MetricType.COMPLETION_RATE]) / len(metrics_by_type[MetricType.COMPLETION_RATE])

        # Compute trends
        analysis.conversion_trend = self._compute_trend(metrics_by_type.get(MetricType.CONVERSIONS, []))
        analysis.revenue_trend = self._compute_trend(metrics_by_type.get(MetricType.REVENUE, []))

        # Generate recommendations
        analysis.recommendations = self._generate_recommendations(analysis)

        return analysis

    @staticmethod
    def _compute_trend(values: List[float]) -> Optional[str]:
        """Determine if values are improving, declining, or stable"""
        if len(values) < 2:
            return None

        # Compare first half vs second half
        mid = len(values) // 2
        first_half_avg = sum(values[:mid]) / mid if mid > 0 else 0
        second_half_avg = sum(values[mid:]) / (len(values) - mid) if len(values) > mid else 0

        if first_half_avg == 0:
            return None

        change = (second_half_avg - first_half_avg) / first_half_avg

        if change > 0.05:
            return "improving"
        elif change < -0.05:
            return "declining"
        else:
            return "stable"

    @staticmethod
    def _generate_recommendations(analysis: PerformanceAnalysis) -> List[str]:
        """Generate optimization recommendations"""
        recommendations = []

        if analysis.conversion_rate is not None:
            if analysis.conversion_rate < 0.01:
                recommendations.append("Low conversion rate (<1%). Review content quality and landing page.")
            elif analysis.conversion_rate > 0.05:
                recommendations.append("High conversion rate (>5%). Consider increasing budget to scale.")

        if analysis.engagement_rate is not None:
            if analysis.engagement_rate < 0.01:
                recommendations.append("Low engagement (<1%). Try different formats or headlines.")
            elif analysis.engagement_rate > 0.1:
                recommendations.append("High engagement (>10%). This format is working well.")

        if analysis.conversion_trend == "declining":
            recommendations.append("Conversion rate is declining. Refresh content or audience.")
        elif analysis.conversion_trend == "improving":
            recommendations.append("Conversion trend improving. Keep current strategy, monitor closely.")

        if analysis.error_rate is not None and analysis.error_rate > 0.05:
            recommendations.append("Error rate >5%. Check system health and error logs.")

        if analysis.avg_response_time is not None and analysis.avg_response_time > 1000:
            recommendations.append("Slow response times (>1s). Optimize engine performance.")

        return recommendations
