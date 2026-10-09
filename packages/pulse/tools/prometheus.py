import json
import math

import httpx


class Prometheus:
    def __init__(self, url):
        self.client = httpx.AsyncClient(base_url=url, timeout=8)

    async def query(self, metric: str, service_name: str, window=60):
        label = json.dumps(service_name)
        selector = f"service={label}"
        expressions = {
            "latency": f"histogram_quantile(0.95, sum by (le) (rate(demo_http_duration_seconds_bucket{{{selector}}}[{window}s]))) * 1000",
            "error_rate": f'sum(rate(demo_http_requests_total{{{selector},status=~"5.."}}[{window}s])) / sum(rate(demo_http_requests_total{{{selector}}}[{window}s]))',
            "cpu": f"pulse_container_cpu_percent{{{selector}}}",
            "memory": f"pulse_container_memory_percent{{{selector}}}",
        }
        if metric not in expressions:
            raise ValueError("Unsupported metric")
        response = await self.client.get("/api/v1/query", params={"query": expressions[metric]})
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "success":
            raise ValueError("Prometheus rejected the query")
        rows = data["data"]["result"]
        values = [float(r["value"][1]) for r in rows]
        return {
            "query": expressions[metric],
            "value": values[0] if values and math.isfinite(values[0]) else None,
            "result": rows,
            "source": "prometheus",
        }

    async def close(self):
        await self.client.aclose()
