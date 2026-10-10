"""Private, project-specific state outside the target repository."""

import hashlib
import json
import os
import secrets
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from pulse.project.scan import PROJECT, compose_services, repository, scan


def home():
    return Path(
        os.getenv("PULSE_HOME")
        or Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local/share") / "pulse"
    )


def location(root):
    root = repository(root)
    identity = hashlib.sha256(os.fsencode(root)).hexdigest()[:24]
    return home() / "projects" / identity


def atomic_json(path, value):
    if path.parent.is_symlink():
        raise RuntimeError("Project state directories cannot use a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError("Project state cannot use a symlink")
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        pending = Path(output.name)
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")
    pending.chmod(0o600)
    os.replace(pending, path)


def endpoint(value):
    if not isinstance(value, str):
        raise RuntimeError("Telemetry URLs must be strings")
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            "Project telemetry URLs must be explicit loopback HTTP(S) URLs without credentials or query parameters"
        )
    try:
        _ = parsed.port
    except ValueError as error:
        raise RuntimeError("Invalid telemetry URL port") from error
    return value


def initialize(
    path, compose_file=None, project=None, recovery_services=(), health_urls=None, prometheus_url=""
):
    folder = location(path)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    if folder.is_symlink():
        raise RuntimeError("Project state directory cannot be a symlink")
    from pulse.project.session import lock

    with lock(folder):
        return _initialize(
            path, compose_file, project, recovery_services, health_urls, prometheus_url
        )


def _initialize(path, compose_file, project, recovery_services, health_urls, prometheus_url):
    root = repository(path)
    folder = location(root)
    profile_path = folder / "profile.json"
    if profile_path.exists():
        if compose_file or project or recovery_services or health_urls or prometheus_url:
            raise RuntimeError(
                "A profile already exists. Review its profile.json locally; existing credentials and history were preserved."
            )
        return load(root)
    inventory = scan(root)
    candidate = compose_file or inventory["compose_file"]
    if not candidate:
        raise RuntimeError(
            "Inventory is available with pulse scan. Live monitoring currently requires a root Docker Compose file, or --compose-file."
        )
    selected = (root / candidate).resolve(strict=True)
    if not selected.is_relative_to(root) or (root / candidate).is_symlink():
        raise RuntimeError("Compose file must be a regular file inside the selected repository")
    services, declared_name = compose_services(selected, root)
    name = project or declared_name or inventory["compose_project"]
    if not PROJECT.fullmatch(name):
        raise RuntimeError("Invalid Compose project name; supply --compose-project")
    if set(recovery_services) - set(services):
        raise RuntimeError("Recovery services must be declared in the selected Compose file")
    if set(health_urls or {}) - set(services):
        raise RuntimeError("Health probes must belong to declared Compose services")
    probes = {key: endpoint(value) for key, value in (health_urls or {}).items()}
    if prometheus_url:
        endpoint(prometheus_url)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    if folder.is_symlink():
        raise RuntimeError("Project state directory cannot be a symlink")
    profile = {
        "version": 1,
        "inventory": inventory,
        "root": str(root),
        "compose_file": selected.relative_to(root).as_posix(),
        "compose_project": name,
        "services": services,
        "recovery_services": sorted(set(recovery_services)),
        "health_urls": probes,
        "prometheus_url": prometheus_url,
    }
    credential_path = folder / "credentials.json"
    if not credential_path.exists():
        atomic_json(
            credential_path,
            {"admin_token": secrets.token_urlsafe(32), "adapter_token": secrets.token_urlsafe(32)},
        )
    else:
        credentials(root)
    override = {
        "services": {
            service: {
                "labels": {
                    "pulse.monitor": "true",
                    **(
                        {"pulse.remediate": "true", "pulse.environment": "development"}
                        if service in recovery_services
                        else {}
                    ),
                }
            }
            for service in services
        }
    }
    atomic_json(folder / "monitor.compose.json", override)
    atomic_json(profile_path, profile)
    return profile


def load(path):
    root = repository(path)
    folder = location(root)
    if (folder / "profile.json").is_symlink() or folder.is_symlink():
        raise RuntimeError("Project state cannot use symlinks")
    try:
        profile = read_json(folder / "profile.json")
    except (OSError, ValueError) as error:
        raise RuntimeError(
            "No valid project profile. Run pulse init in this repository."
        ) from error
    if (
        not isinstance(profile, dict)
        or profile.get("version") != 1
        or profile.get("root") != str(root)
        or not isinstance(profile.get("compose_project"), str)
        or not PROJECT.fullmatch(profile["compose_project"])
        or not isinstance(profile.get("inventory"), dict)
        or profile["inventory"].get("id") != folder.name
        or not isinstance(profile.get("compose_file"), str)
        or not isinstance(profile.get("recovery_services"), list)
        or any(not isinstance(item, str) for item in profile["recovery_services"])
        or not isinstance(profile.get("prometheus_url"), str)
    ):
        raise RuntimeError("Project profile identity is invalid; no monitoring was started")
    services, _ = compose_services(root / profile["compose_file"], root)
    if services != profile.get("services") or not set(
        profile.get("recovery_services", [])
    ).issubset(services):
        raise RuntimeError(
            "Compose services changed. Review the saved profile before monitoring a new scope."
        )
    probes = profile.get("health_urls", {})
    if not isinstance(probes, dict) or set(probes) - set(services):
        raise RuntimeError("Health probes are outside the selected service allowlist")
    for value in probes.values():
        endpoint(value)
    if profile.get("prometheus_url"):
        endpoint(profile["prometheus_url"])
    return profile


def credentials(path):
    target = location(path) / "credentials.json"
    if target.is_symlink():
        raise RuntimeError("Project credentials cannot use a symlink")
    data = read_json(target)
    if (
        not isinstance(data, dict)
        or any(
            not isinstance(data.get(key), str) or len(data[key]) < 16
            for key in ("admin_token", "adapter_token")
        )
        or data["admin_token"] == data["adapter_token"]
    ):
        raise RuntimeError(
            "Project credentials are invalid; existing credentials were not replaced"
        )
    return data


def read_json(path):
    if path.is_symlink() or path.parent.is_symlink():
        raise RuntimeError("Project state cannot use symlinks")
    if path.stat().st_size > 1024 * 1024:
        raise RuntimeError("Project state exceeds the 1 MiB read limit")
    with path.open("rb") as source:
        raw = source.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise RuntimeError("Project state exceeds the 1 MiB read limit")
    return json.loads(raw)
