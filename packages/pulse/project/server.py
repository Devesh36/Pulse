"""API child for a terminal-owned project session; target code is never imported."""

import argparse
from pathlib import Path
from typing import cast

import uvicorn
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI

from pulse.project.guard import parent_guard


class ProjectServer(uvicorn.Server):
    def handle_exit(self, sig, frame):
        cast(FastAPI, self.config.app).state.draining = True
        super().handle_exit(sig, frame)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    from pulse.db import store as storage

    migration = AlembicConfig()
    migration.set_main_option("script_location", str(Path(storage.__file__).parent / "migrations"))
    command.upgrade(migration, "head")
    from apps.api.main import app

    with parent_guard():
        ProjectServer(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=args.port,
                access_log=False,
                log_level="warning",
                timeout_graceful_shutdown=5,
            )
        ).run()


if __name__ == "__main__":
    main()
