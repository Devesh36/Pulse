"""Bounded metadata inventory. Never execute a target repository or read its secrets."""

import hashlib
import json
import os
import re
import tomllib
from pathlib import Path

import yaml
from yaml.events import AliasEvent

COMPOSE = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
MANIFESTS = {
    "package.json": "JavaScript / TypeScript",
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
    "go.mod": "Go",
    "Cargo.toml": "Rust",
    "pom.xml": "Java",
    "build.gradle": "Java / Kotlin",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "Dockerfile": "Docker",
}
SKIP = {"node_modules", "vendor", "dist", "build", "target", "coverage", "__pycache__"}
NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")
PROJECT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")
LIMIT = 1024 * 1024


def repository(path):
    root = Path(path).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise RuntimeError("Choose a repository directory")
    return root


def read_metadata(path, root):
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise RuntimeError("Metadata symlinks are not scanned")
    if not path.is_file() or path.stat().st_size > LIMIT:
        raise RuntimeError("Metadata file is unavailable or exceeds 1 MiB")
    with path.open("rb") as source:
        raw = source.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise RuntimeError("Metadata exceeds 1 MiB")
    return raw.decode("utf-8")


def compose_services(path, root):
    text = read_metadata(path, root)
    # Refuse aliases/custom constructors and bound token count before constructing data.
    events = 0
    depth = 0
    for event in yaml.parse(text):
        events += 1
        if isinstance(event, AliasEvent) or events > 20000:
            raise RuntimeError("Compose aliases or oversized structures require manual review")
        if isinstance(event, (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent)):
            depth += 1
        elif isinstance(event, (yaml.events.MappingEndEvent, yaml.events.SequenceEndEvent)):
            depth -= 1
        if depth > 40:
            raise RuntimeError("Compose nesting exceeds the scan limit")
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or not isinstance(data.get("services"), dict):
        raise RuntimeError("Compose file must declare services")
    if data.get("include"):
        raise RuntimeError(
            "Compose include files require explicit review; use a self-contained file"
        )
    services = data["services"]
    if not 1 <= len(services) <= 100 or any(
        not isinstance(name, str) or not NAME.fullmatch(name) for name in services
    ):
        raise RuntimeError("Compose service names are invalid or exceed the 100-service limit")
    if any(not isinstance(value, dict) or value.get("extends") for value in services.values()):
        raise RuntimeError("Compose service definitions or extends require manual review")
    name = data.get("name")
    return sorted(services), name if isinstance(name, str) and PROJECT.fullmatch(name) else None


def scan(path):
    root = repository(path)
    found, warnings, languages, frameworks = [], [], set(), set()
    visited = 0

    def unavailable(error):
        warnings.append("A directory was unavailable; the inventory is incomplete.")

    for folder, dirs, files in os.walk(root, followlinks=False, onerror=unavailable):
        current = Path(folder)
        depth = len(current.relative_to(root).parts)
        if depth == 4 and dirs:
            warnings.append(f"Skipped deeper directories beneath {current.relative_to(root)}.")
        dirs[:] = (
            sorted(
                d
                for d in dirs
                if not d.startswith(".") and d not in SKIP and not (current / d).is_symlink()
            )
            if depth < 4
            else []
        )
        for name in sorted(files):
            visited += 1
            if visited > 5000:
                warnings.append(
                    "Inventory stopped at 5,000 files; deeper or remaining files were not scanned."
                )
                break
            if name not in MANIFESTS and name not in COMPOSE:
                continue
            candidate = current / name
            relative = candidate.relative_to(root).as_posix()
            if candidate.is_symlink():
                warnings.append(f"Skipped metadata symlink: {relative}")
                continue
            found.append(relative)
            if name in MANIFESTS:
                languages.add(MANIFESTS[name])
            try:
                if name == "package.json":
                    document = json.loads(read_metadata(candidate, root))
                    deps = {
                        **document.get("dependencies", {}),
                        **document.get("devDependencies", {}),
                    }
                    frameworks.update(
                        label
                        for key, label in {
                            "next": "Next.js",
                            "react": "React",
                            "express": "Express",
                            "fastify": "Fastify",
                        }.items()
                        if key in deps
                    )
                elif name == "pyproject.toml":
                    document = tomllib.loads(read_metadata(candidate, root))
                    deps = document.get("project", {}).get("dependencies", [])
                    if isinstance(deps, list):
                        for key, label in {
                            "fastapi": "FastAPI",
                            "django": "Django",
                            "flask": "Flask",
                        }.items():
                            if any(
                                isinstance(item, str) and re.match(rf"^{key}(?:\b|\[)", item, re.I)
                                for item in deps
                            ):
                                frameworks.add(label)
            except (RuntimeError, OSError, ValueError, TypeError, AttributeError):
                warnings.append(f"Could not safely inventory {relative}; inspect it locally.")
        if visited > 5000:
            break
    compose = next((name for name in COMPOSE if (root / name).is_file()), None)
    services, project_name = [], None
    if compose:
        try:
            services, project_name = compose_services(root / compose, root)
        except (RuntimeError, OSError, yaml.YAMLError, UnicodeError):
            warnings.append("The root Compose file needs manual review before enrollment.")
    default_name = re.sub(r"[^a-z0-9_-]", "", root.name.lower()).lstrip("-_") or "project"
    return {
        "id": hashlib.sha256(os.fsencode(root)).hexdigest()[:24],
        "name": root.name,
        "root": str(root),
        "languages": sorted(languages),
        "frameworks": sorted(frameworks),
        "metadata_files": found,
        "compose_file": compose,
        "compose_project": project_name or default_name[:128],
        "services": services,
        "warnings": warnings,
        "scope": "Metadata inventory only; not a source-code security audit or live health assessment.",
    }
