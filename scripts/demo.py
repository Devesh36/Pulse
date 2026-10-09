"""Authenticated fault controls for the local demo; never connects to other services."""

import argparse
import asyncio
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


async def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=["crash", "memory", "latency", "errors", "reset"])
    parser.add_argument("--mib", type=int, default=160)
    parser.add_argument("--delay", type=float, default=2)
    args = parser.parse_args()
    env = dotenv_values(ROOT / ".env")
    token = env.get("PULSE_DEMO_TOKEN")
    if not token:
        raise SystemExit("Configure .env with scripts/setup-env.py first")
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8030", timeout=10) as client:
        path = "/reset" if args.scenario == "reset" else f"/fault/{args.scenario}"
        response = await client.post(
            path,
            headers={"X-Demo-Token": token},
            json={"mib": args.mib, "delay_seconds": args.delay},
        )
        response.raise_for_status()
        print(response.json())


if __name__ == "__main__":
    asyncio.run(run())
