"""Single-worker API entry point that drains SSE before Uvicorn waits for connections."""

import argparse

import uvicorn

from apps.api.main import app


class PulseServer(uvicorn.Server):
    def handle_exit(self, sig, frame):
        app.state.draining = True
        super().handle_exit(sig, frame)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = PulseServer(
        uvicorn.Config(
            app, host=args.host, port=args.port, timeout_graceful_shutdown=10, access_log=False
        )
    )
    server.run()


if __name__ == "__main__":
    main()
