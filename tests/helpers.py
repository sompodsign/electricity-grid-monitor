from pathlib import Path

from grid_monitor.config import Settings


def settings(database_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_path": database_path,
        "poll_interval_seconds": 1.0,
        "power_supply_path": Path("/fake/AC"),
        "notification_enabled": False,
        "email_notification_enabled": True,
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_username": "",
        "smtp_password": "",
        "smtp_from_email": "",
        "notification_to_email": "",
        "smtp_use_tls": True,
        "smtp_use_ssl": False,
        "telegram_enabled": False,
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "notification_language": "en",
        "site_name": "Test Grid",
        "timezone": "UTC",
        "dashboard_username": "",
        "dashboard_password": "",
        "battery_warning_percent": 15,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]
