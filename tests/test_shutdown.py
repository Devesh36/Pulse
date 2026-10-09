import asyncio
import os
import signal
import sys

import httpx


async def test_server_drains_authenticated_sse_on_shutdown(config, store, unused_tcp_port):
    env = {
        **os.environ,
        "PULSE_DATABASE_URL": config.database_url,
        "PULSE_ADMIN_TOKEN": config.admin_token,
        "PULSE_ADAPTER_TOKEN": config.adapter_token,
        "PULSE_MONITOR_ENABLED": "false",
        "PULSE_LLM_MODEL": "",
        "PULSE_PROBE_URLS": "{}",
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "apps.api.serve",
        "--port",
        str(unused_tcp_port),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{unused_tcp_port}", timeout=4
        ) as client:
            for _ in range(40):
                try:
                    response = await client.get("/api/v1/health")
                    if response.status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                await asyncio.sleep(0.1)
            else:
                raise AssertionError("API did not start")
            async with client.stream(
                "GET", "/api/v1/events", headers={"Authorization": f"Bearer {config.admin_token}"}
            ) as stream:
                assert stream.status_code == 200
                iterator = stream.aiter_lines()
                assert await anext(iterator) == "event: sync"
                process.terminate()
                await asyncio.wait_for(process.wait(), 7)
                assert process.returncode in (0, -signal.SIGTERM)
                _, errors = await process.communicate()
                assert b"Application shutdown complete" in errors and b"Traceback" not in errors
                await asyncio.wait_for(iterator.aclose(), 2)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
