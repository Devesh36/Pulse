import json
import math
import time

import httpx


class UnconfiguredPrometheus:
    def __init__(self):
        self.max_age_seconds = 30

    async def query(self, metric, service_name, window=60):
        return {
            "value": None,
            "result": [],
            "source": "prometheus",
            "available": False,
            "sample_at": None,
            "observed_at": time.time(),
            "service": service_name,
            "metric": metric,
            "reason": "Prometheus is not configured for this project",
        }

    async def close(self):
        pass


class Prometheus:
    def __init__(self, url, max_age_seconds=30):
        self.client = httpx.AsyncClient(base_url=url, timeout=8)
        self.max_age_seconds = max_age_seconds

    async def query(self, metric: str, service_name: str, window=60):
        window = max(2, min(3600, int(window)))
        label = json.dumps(service_name)
        selector = f"service={label}"
        expressions = {
            "latency": f"histogram_quantile(0.95, sum by (le) (rate(demo_http_duration_seconds_bucket{{{selector}}}[{window}s]))) * 1000",
            "error_rate": f'sum(rate(demo_http_requests_total{{{selector},status=~"5.."}}[{window}s])) / sum(rate(demo_http_requests_total{{{selector}}}[{window}s]))',
            "cpu": f"pulse_container_cpu_percent{{{selector}}}",
            "memory": f"pulse_container_memory_percent{{{selector}}}",
            "request_count": f"sum(increase(demo_http_requests_total{{{selector}}}[{window}s]))",
        }
        if metric not in expressions:
            raise ValueError("Unsupported metric")
        evaluated_at = time.time()
        response = await self.client.get(
            "/api/v1/query", params={"query": expressions[metric], "time": evaluated_at}
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "success":
            raise ValueError("Prometheus rejected the query")
        rows = data["data"]["result"]
        values = [float(r["value"][1]) for r in rows]
        sample_at = float(rows[0]["value"][0]) if rows else None
        if metric in ("latency", "error_rate", "request_count"):
            source_metric = (
                "demo_http_duration_seconds_bucket"
                if metric == "latency"
                else "demo_http_requests_total"
            )
            source = f"{source_metric}{{{selector}}}"
            freshness = await self.client.get(
                "/api/v1/query",
                params={
                    "query": f"min(timestamp({source})) and on() (min(up and on(job, instance) {source}) == 1)",
                    "time": evaluated_at,
                },
            )
            freshness.raise_for_status()
            scraped = freshness.json()["data"]["result"]
            sample_at = float(scraped[0]["value"][1]) if scraped else None
        fresh = sample_at is not None and -5 <= time.time() - sample_at <= self.max_age_seconds
        return {
            "query": expressions[metric],
            "value": values[0] if values and math.isfinite(values[0]) and fresh else None,
            "result": rows,
            "source": "prometheus",
            "sample_at": sample_at,
            "observed_at": time.time(),
            "available": fresh and bool(values) and math.isfinite(values[0]),
            "window_seconds": window,
            "window_started_at": evaluated_at - window,
            "evaluated_at": evaluated_at,
            "service": service_name,
            "metric": metric,
        }

    async def close(self):
        await self.client.aclose()
