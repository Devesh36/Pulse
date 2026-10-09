"""Real Docker/PostgreSQL acceptance demo. Requires running Compose with the demo profile.

The operator explicitly approves exactly the action found for the injected demo crash.
"""

import asyncio
import json
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


async def wait_for(fetch, predicate, description, deadline_seconds=180):
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        try:
            value = await fetch()
        except httpx.RequestError:
            await asyncio.sleep(2)
            continue
        except httpx.HTTPStatusError as error:
            if error.response.status_code < 500:
                raise
            await asyncio.sleep(2)
            continue
        if predicate(value):
            return value
        await asyncio.sleep(2)
    raise RuntimeError(f"Timed out waiting for {description}")


async def main():
    env = dotenv_values(ROOT / ".env")
    if not env.get("PULSE_ADMIN_TOKEN") or not env.get("PULSE_DEMO_TOKEN"):
        raise RuntimeError("Run scripts/setup-env.py first")
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000/api/v1",
        timeout=15,
        headers={"Authorization": f"Bearer {env['PULSE_ADMIN_TOKEN']}"},
    ) as api:

        async def get(path):
            response = await api.get(path)
            response.raise_for_status()
            return response.json()

        services = await wait_for(
            lambda: get("/services"),
            lambda rows: any(
                s["snapshot"].get("labels", {}).get("com.docker.compose.service") == "faulty-app"
                for s in rows
            ),
            "Docker discovery",
        )
        service = next(
            s
            for s in services
            if s["snapshot"].get("labels", {}).get("com.docker.compose.service") == "faulty-app"
        )
        if service["snapshot"]["status"] != "running":
            raise RuntimeError("Start a healthy demo container before running this test")
        original_settings = (await get("/settings"))["runtime"]
        original_permissions = {k: service[k] for k in ("monitored", "remediation_allowed")}
        # Use the actual policy and explicit approval endpoints, not an adapter shortcut.
        settings = {
            **original_settings,
            "interval_seconds": 2,
            "verification_seconds": 10,
            "recovery_grace_seconds": 20,
            "min_samples": 1,
            "remediation_disabled": False,
        }
        response = await api.patch("/settings", json=settings)
        response.raise_for_status()
        response = await api.patch(
            f"/services/{service['id']}/permissions",
            json={"monitored": True, "remediation_allowed": True},
        )
        response.raise_for_status()
        try:
            started = time.time()
            async with httpx.AsyncClient(base_url="http://127.0.0.1:8030", timeout=5) as demo:
                response = await demo.post(
                    "/fault/crash", json={}, headers={"X-Demo-Token": env["PULSE_DEMO_TOKEN"]}
                )
                response.raise_for_status()
            print("Real demo fault injected; process exits with code 42.")
            rows = await wait_for(
                lambda: get("/incidents"),
                lambda rows: any(
                    i["service_id"] == service["id"]
                    and i["kind"] == "stopped"
                    and i["created_at"] >= started
                    and i["state"] == "AWAITING_APPROVAL"
                    for i in rows
                ),
                "diagnosis and approval request",
            )
            incident = next(
                i
                for i in rows
                if i["service_id"] == service["id"]
                and i["kind"] == "stopped"
                and i["created_at"] >= started
            )
            detail = await get(f"/incidents/{incident['id']}")
            assert detail["diagnosis"] and any(
                f["evidence_ids"] for f in detail["diagnosis"]["root_causes"]
            )
            assert any(
                t["name"] == "inspect_container" and t["result"].get("exit_code") == 42
                for t in detail["tools"]
            )
            assert any(
                t["name"] == "get_container_logs" and "application_crash" in str(t["result"])
                for t in detail["tools"]
            )
            action = next(
                a for a in detail["actions"] if a["status"] == "proposed" and a["kind"] == "start"
            )
            print(
                "Evidence-backed diagnosis verified. Explicitly approving the reviewed demo start action."
            )
            approved = await api.post(
                f"/remediations/{action['id']}/approve", json={"action_digest": action["digest"]}
            )
            approved.raise_for_status()
            replay = await api.post(
                f"/remediations/{action['id']}/approve", json={"action_digest": action["digest"]}
            )
            assert replay.status_code == 409, "Duplicate approval was not blocked"
            final = await wait_for(
                lambda: get(f"/incidents/{incident['id']}"),
                lambda i: i["state"] in ("RESOLVED", "FAILED"),
                "sustained recovery",
            )
            if final["state"] != "RESOLVED":
                raise RuntimeError(f"Recovery not confirmed: {json.dumps(final['verification'])}")
            assert (
                final["verification"]["outcome"] == "confirmed"
                and len(final["verification"]["samples"]) >= 2
            )
            print(
                json.dumps(
                    {
                        "result": "PASS",
                        "incident_id": final["id"],
                        "state": final["state"],
                        "tool_executions": len(final["tools"]),
                        "verification_samples": len(final["verification"]["samples"]),
                        "observation_seconds": final["verification"]["observation_seconds"],
                    },
                    indent=2,
                )
            )
        finally:
            await api.patch("/settings", json=original_settings)
            await api.patch(f"/services/{service['id']}/permissions", json=original_permissions)


if __name__ == "__main__":
    asyncio.run(main())
