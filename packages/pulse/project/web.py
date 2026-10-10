"""The installed local project dashboard uses the existing authenticated APIs."""

from pathlib import Path

from fastapi.responses import FileResponse

from pulse.core.redaction import redact

ASSETS = Path(__file__).parent / "assets"


def attach(app, config, auth):
    @app.get("/api/v1/project/identity", include_in_schema=False)
    async def identity():
        # Public opaque identity lets a local CLI check the port before sending credentials.
        return {"project_id": config.project_context["inventory"]["id"]}

    @app.get("/", include_in_schema=False)
    async def dashboard():
        return FileResponse(ASSETS / "dashboard.html", headers={"Cache-Control": "no-store"})

    @app.get("/_pulse/dashboard.css", include_in_schema=False)
    async def stylesheet():
        return FileResponse(ASSETS / "dashboard.css")

    @app.get("/_pulse/dashboard.js", include_in_schema=False)
    async def javascript():
        return FileResponse(ASSETS / "dashboard.js", media_type="text/javascript")

    @app.get("/api/v1/project", dependencies=auth)
    async def project():
        return redact(config.project_context)
