"""Materialize the installed public project bundle while preserving user state."""

import hashlib
import os
import tempfile
from importlib import resources
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


def materialize(payload: bytes, destination: Path) -> Path:
    digest = hashlib.sha256(payload).hexdigest()
    marker = destination / ".pulse-bundle-sha256"
    if marker.exists() and marker.read_text() == digest:
        return destination
    with ZipFile(BytesIO(payload)) as archive:
        entries = archive.infolist()
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in entry.filename
                or ".env" in path.parts
                or "reports" in path.parts
                or entry.is_dir()
                or not path.parts
            ):
                raise RuntimeError("Invalid public demo bundle; reinstall Pulse")
        destination.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            target = destination / entry.filename
            if not target.resolve().is_relative_to(destination.resolve()):
                raise RuntimeError("Demo bundle destination contains an unsafe symlink")
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
                pending = Path(output.name)
                output.write(archive.read(entry))
            pending.chmod(0o644)
            os.replace(pending, target)
    marker.write_text(digest)
    return destination


def project_root() -> Path:
    checkout = Path(__file__).resolve().parents[2]
    if (checkout / "pyproject.toml").exists() and (
        checkout / "examples/incident-lab/docker-compose.yml"
    ).exists():
        return checkout
    bundle = resources.files("pulse").joinpath("resources/project.zip")
    if not bundle.is_file():
        raise RuntimeError("This installation has no demo bundle; reinstall pulse-sre with uv")
    home = Path(
        os.environ.get("PULSE_HOME")
        or Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "pulse"
    )
    return materialize(bundle.read_bytes(), home / "project")
