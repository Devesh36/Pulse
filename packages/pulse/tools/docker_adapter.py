import asyncio
import time

import httpx

from pulse.core.config import Config


class AdapterError(RuntimeError):
    pass


class DockerAdapter:
    def __init__(self, config: Config):
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.adapter_url,
            timeout=config.tool_timeout,
            headers={"Authorization": f"Bearer {config.adapter_token}"},
        )

    async def request(self, method, path, **kwargs):
        try:
            response = await self.client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise AdapterError(f"Docker adapter unavailable ({type(error).__name__})") from error

    async def discover(self):
        return await self.request("GET", "/containers")

    async def inspect(self, cid):
        return await self.request("GET", f"/containers/{cid}")

    async def logs(self, cid, since=1800, limit=100):
        return await self.request(
            "GET", f"/containers/{cid}/logs", params={"since": since, "limit": limit}
        )

    async def metrics(self, cid):
        return await self.request("GET", f"/containers/{cid}/metrics")

    async def mutate(self, cid, kind, action_id):
        return await self.request(
            "POST", f"/containers/{cid}/{kind}", json={"action_id": action_id}
        )

    async def close(self):
        await self.client.aclose()


class SDKAdapter:
    """Used only in the isolated gateway. Docker metadata never includes environment or mounts."""

    def __init__(self, client):
        self.client = client

    def container(self, cid):
        container = self.client.containers.get(cid)
        container.reload()
        if container.labels.get("pulse.monitor") != "true":
            raise PermissionError("Container is outside the gateway monitoring allowlist")
        return container

    def snapshot(self, container):
        attrs = container.attrs
        state = attrs.get("State", {})
        labels = {
            k: str(v)[:512]
            for k, v in container.labels.items()
            if k
            in {
                "pulse.monitor",
                "pulse.remediate",
                "pulse.environment",
                "pulse.dependencies",
                "com.docker.compose.service",
                "com.docker.compose.project",
                "com.docker.compose.config-hash",
            }
        }
        health = state.get("Health", {})
        return {
            "container_id": container.id,
            "name": container.name,
            "status": state.get("Status", "unknown"),
            "health": health.get("Status", "none"),
            "health_log": [
                {**entry, "Output": str(entry.get("Output", ""))[:2000]}
                for entry in health.get("Log", [])[-3:]
            ],
            "restart_count": attrs.get("RestartCount", 0),
            "exit_code": state.get("ExitCode", 0),
            "oom_killed": state.get("OOMKilled", False),
            "error": state.get("Error", ""),
            "started_at": state.get("StartedAt"),
            "finished_at": state.get("FinishedAt"),
            "created_at": attrs.get("Created"),
            "image": attrs.get("Config", {}).get("Image", ""),
            "labels": labels,
            "observed_at": time.time(),
        }

    def discover(self):
        return [
            self.snapshot(c)
            for c in self.client.containers.list(all=True, filters={"label": "pulse.monitor=true"})
        ]

    def inspect(self, cid):
        return self.snapshot(self.container(cid))

    def logs(self, cid, since=1800, limit=100):
        stream = self.container(cid).logs(
            since=int(time.time() - since), tail=limit, timestamps=True, stream=True, follow=False
        )
        raw = bytearray()
        truncated = False
        try:
            for chunk in stream:
                remaining = 65536 - len(raw)
                raw.extend(chunk[:remaining])
                if len(chunk) >= remaining:
                    truncated = True
                    break
        finally:
            if hasattr(stream, "close"):
                stream.close()
        return {
            "lines": raw.decode("utf-8", errors="replace").splitlines()[-limit:],
            "truncated": truncated,
        }

    def metrics(self, cid):
        c = self.container(cid)
        if c.status != "running":
            return {"available": False, "reason": f"container is {c.status}"}
        s = c.stats(stream=False)
        cpu = s.get("cpu_stats", {})
        prev = s.get("precpu_stats", {})
        delta = cpu.get("cpu_usage", {}).get("total_usage", 0) - prev.get("cpu_usage", {}).get(
            "total_usage", 0
        )
        system = cpu.get("system_cpu_usage", 0) - prev.get("system_cpu_usage", 0)
        cores = cpu.get("online_cpus") or len(cpu.get("cpu_usage", {}).get("percpu_usage", [])) or 1
        mem = s.get("memory_stats", {})
        used = max(0, mem.get("usage", 0) - mem.get("stats", {}).get("inactive_file", 0))
        limit = mem.get("limit", 0)
        return {
            "available": True,
            "cpu_percent": max(0, delta / system * cores * 100) if system > 0 else 0,
            "memory_bytes": used,
            "memory_limit_bytes": limit,
            "memory_percent": used / limit * 100 if limit else 0,
            "at": time.time(),
        }

    def mutate(self, cid, kind):
        c = self.container(cid)
        if (
            c.labels.get("pulse.remediate") != "true"
            or c.labels.get("pulse.environment") != "development"
        ):
            raise PermissionError("Only explicitly approved development containers may be changed")
        if kind == "start" and c.status not in ("exited", "created"):
            raise ValueError("Start requires a stopped container")
        if kind == "restart" and c.status != "running":
            raise ValueError("Restart requires a running container")
        if kind == "start":
            c.start()
        elif kind == "restart":
            c.restart(timeout=10)
        else:
            raise ValueError("Unsupported mutation")
        return self.inspect(cid)


async def run_sdk(fn, *args):
    return await asyncio.to_thread(fn, *args)
