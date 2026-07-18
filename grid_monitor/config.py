from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


TRUTHY = {"1", "true", "yes", "on", "enabled"}
FALSY = {"0", "false", "no", "off", "disabled"}


def load_dotenv(path: Path) -> None:
    """Load a small, predictable subset of dotenv syntax without a dependency."""
    if not path.exists():
        return
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            raise ValueError(f"Invalid .env entry on line {line_number}")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in TRUTHY:
        return True
    if normalized in FALSY:
        return False
    raise ValueError(f"{name} must be one of: {', '.join(sorted(TRUTHY | FALSY))}")


@dataclass(frozen=True)
class Settings:
    database_path: Path
    poll_interval_seconds: float
    power_supply_path: Path | None
    notification_enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from_email: str
    notification_to_email: str
    smtp_use_tls: bool
    smtp_use_ssl: bool
    site_name: str
    timezone: str
    dashboard_username: str
    dashboard_password: str

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        if env_file is None:
            env_file = Path.cwd() / ".env"
        load_dotenv(env_file)

        supply = os.getenv("POWER_SUPPLY_PATH", "").strip()
        settings = cls(
            database_path=Path(os.getenv("DATABASE_PATH", "data/grid_monitor.db")).expanduser(),
            poll_interval_seconds=float(os.getenv("POLL_INTERVAL_SECONDS", "5")),
            power_supply_path=Path(supply).expanduser() if supply else None,
            notification_enabled=env_bool("NOTIFICATION_ENABLED"),
            smtp_host=os.getenv("SMTP_HOST", "").strip(),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_username=os.getenv("SMTP_USERNAME", "").strip(),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            smtp_from_email=os.getenv("SMTP_FROM_EMAIL", "").strip(),
            notification_to_email=os.getenv("NOTIFICATION_TO_EMAIL", "").strip(),
            smtp_use_tls=env_bool("SMTP_USE_TLS", True),
            smtp_use_ssl=env_bool("SMTP_USE_SSL", False),
            site_name=os.getenv("SITE_NAME", "Home Grid").strip() or "Home Grid",
            timezone=os.getenv("TZ", "").strip(),
            dashboard_username=os.getenv("DASHBOARD_USERNAME", "").strip(),
            dashboard_password=os.getenv("DASHBOARD_PASSWORD", ""),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.poll_interval_seconds <= 0:
            raise ValueError("POLL_INTERVAL_SECONDS must be greater than zero")
        if not 1 <= self.smtp_port <= 65535:
            raise ValueError("SMTP_PORT must be between 1 and 65535")
        if self.smtp_use_ssl and self.smtp_use_tls:
            raise ValueError("SMTP_USE_SSL and SMTP_USE_TLS cannot both be enabled")
        if self.notification_enabled:
            required = {
                "SMTP_HOST": self.smtp_host,
                "SMTP_FROM_EMAIL": self.smtp_from_email,
                "NOTIFICATION_TO_EMAIL": self.notification_to_email,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(
                    "Notifications are enabled, but these settings are missing: "
                    + ", ".join(missing)
                )
        if bool(self.dashboard_username) != bool(self.dashboard_password):
            raise ValueError(
                "DASHBOARD_USERNAME and DASHBOARD_PASSWORD must both be set or both be empty"
            )
