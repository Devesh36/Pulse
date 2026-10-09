"""Bundle only public runtime/demo assets, including in Git-based uv installations."""

import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        root = Path(self.root)
        if self.target_name != "wheel" or not (root / "examples/incident-lab").is_dir():
            return
        singles = [
            "pyproject.toml",
            "uv.lock",
            "alembic.ini",
            ".dockerignore",
            "scripts/build-hook.py",
            "apps/__init__.py",
            "apps/api/Dockerfile",
            "apps/web/Dockerfile",
            "apps/web/package.json",
            "apps/web/package-lock.json",
            "apps/web/next.config.ts",
            "apps/web/tsconfig.json",
            "apps/web/postcss.config.mjs",
            "apps/web/next-env.d.ts",
            "apps/web/scripts/start.mjs",
            "examples/incident-lab/docker-compose.yml",
            "examples/incident-lab/services/Dockerfile",
        ]
        trees = [
            "packages/pulse",
            "apps/api",
            "apps/web/src",
            "examples/incident-lab/fixtures",
            "examples/incident-lab/services",
            "examples/incident-lab/telemetry",
        ]
        suffixes = {".py", ".tsx", ".ts", ".css", ".json", ".yml", ".mako", ".in", ".lock"}
        files = {root / name for name in singles if (root / name).is_file()}
        for tree in trees:
            files.update(
                path
                for path in (root / tree).rglob("*")
                if path.is_file()
                and path.suffix in suffixes
                and not any(
                    part.startswith(".") or part in {"__pycache__", "resources"}
                    for part in path.relative_to(root).parts
                )
            )
        self.bundle_directory = tempfile.TemporaryDirectory(prefix="pulse-build-")
        bundle = Path(self.bundle_directory.name) / "project.zip"
        with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
            for path in sorted(files):
                archive.write(path, path.relative_to(root).as_posix())
        build_data.setdefault("force_include", {})[str(bundle)] = "pulse/resources/project.zip"

    def finalize(self, version, build_data, artifact_path):
        directory = getattr(self, "bundle_directory", None)
        if directory:
            directory.cleanup()
