"""Create local credentials without printing them. Preserve existing .env configuration."""

import os
import secrets
from pathlib import Path

from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
path = root / ".env"
values = dotenv_values(path if path.exists() else root / ".env.example")
for key in ("PULSE_ADMIN_TOKEN", "PULSE_ADAPTER_TOKEN", "POSTGRES_PASSWORD", "PULSE_DEMO_TOKEN"):
    if not values.get(key):
        values[key] = secrets.token_hex(32)
if (
    not values.get("PULSE_DATABASE_URL")
    or "replace-with-POSTGRES_PASSWORD" in values["PULSE_DATABASE_URL"]
):
    values["PULSE_DATABASE_URL"] = (
        f"postgresql+psycopg://pulse:{values['POSTGRES_PASSWORD']}@localhost:5432/pulse"
    )
content = "\n".join(f"{key}='{value or ''}'" for key, value in values.items()) + "\n"
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as file:
    file.write(content)
os.chmod(path, 0o600)
print("Configured .env with unique local credentials (mode 0600). Existing settings preserved.")
