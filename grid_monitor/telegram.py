from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings
from .models import PowerEvent, PowerState


def format_telegram_time(event: PowerEvent, timezone_name: str) -> tuple[str, str]:
    timestamp = event.timestamp
    if timezone_name:
        try:
            timestamp = timestamp.astimezone(ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown TZ value: {timezone_name}") from exc

    offset = timestamp.strftime("%z")
    timezone_label = (
        f"UTC{offset[:3]}:{offset[3:]}" if offset else timestamp.tzname() or "local time"
    )
    date_text = timestamp.strftime("%A, %d %B %Y")
    time_text = timestamp.strftime("%I:%M:%S %p").lstrip("0")
    return date_text, f"{time_text} ({timezone_label})"


def build_telegram_text(event: PowerEvent, settings: Settings) -> str:
    is_on = event.state is PowerState.ON
    icon = "⚡" if is_on else "⚠️"
    headline = "Electricity Restored" if is_on else "Power Outage"
    detail = (
        "Mains power is available again."
        if is_on
        else "Mains power is unavailable."
    )
    date_text, time_text = format_telegram_time(event, settings.timezone)
    return (
        f"{icon} {headline}\n\n"
        f"📍 {settings.site_name}\n"
        f"📅 {date_text}\n"
        f"🕐 {time_text}\n"
        f"🔌 Source: {event.source}\n\n"
        f"{'✅' if is_on else '❌'} {detail}"
    )


def send_telegram_notification(event: PowerEvent, settings: Settings) -> None:
    endpoint = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": settings.telegram_chat_id,
            "text": build_telegram_text(event, settings),
        }
    ).encode("utf-8")
    request = Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"Telegram API returned HTTP {exc.code}") from None
    except URLError as exc:
        raise RuntimeError("Could not connect to the Telegram API") from None
    if not result.get("ok"):
        description = result.get("description", "unknown Telegram API error")
        raise RuntimeError(f"Telegram API rejected the message: {description}")
