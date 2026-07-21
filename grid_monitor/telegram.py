from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings
from .models import PowerEvent, PowerState


BANGLA_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
BANGLA_WEEKDAYS = (
    "সোমবার",
    "মঙ্গলবার",
    "বুধবার",
    "বৃহস্পতিবার",
    "শুক্রবার",
    "শনিবার",
    "রবিবার",
)
BANGLA_MONTHS = (
    "জানুয়ারি",
    "ফেব্রুয়ারি",
    "মার্চ",
    "এপ্রিল",
    "মে",
    "জুন",
    "জুলাই",
    "আগস্ট",
    "সেপ্টেম্বর",
    "অক্টোবর",
    "নভেম্বর",
    "ডিসেম্বর",
)


def format_telegram_time(
    event: PowerEvent, timezone_name: str, language: str = "en"
) -> tuple[str, str]:
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
    if language == "bn":
        date_text = (
            f"{BANGLA_WEEKDAYS[timestamp.weekday()]}, {timestamp.day} "
            f"{BANGLA_MONTHS[timestamp.month - 1]} {timestamp.year}"
        ).translate(BANGLA_DIGITS)
        hour = timestamp.hour
        period = (
            "রাত" if hour < 4 or hour >= 20 else
            "ভোর" if hour < 6 else
            "সকাল" if hour < 12 else
            "দুপুর" if hour < 16 else
            "বিকেল" if hour < 18 else
            "সন্ধ্যা"
        )
        hour_12 = hour % 12 or 12
        clock = f"{hour_12}:{timestamp.minute:02d}:{timestamp.second:02d}".translate(
            BANGLA_DIGITS
        )
        time_text = f"{period} {clock}"
    else:
        date_text = timestamp.strftime("%A, %d %B %Y")
        time_text = timestamp.strftime("%I:%M:%S %p").lstrip("0")
    return date_text, f"{time_text} ({timezone_label})"


def build_telegram_text(event: PowerEvent, settings: Settings) -> str:
    is_on = event.state is PowerState.ON
    is_bangla = settings.notification_language == "bn"
    icon = "⚡" if is_on else "⚠️"
    if is_bangla:
        headline = "বিদ্যুৎ ফিরে এসেছে" if is_on else "বিদ্যুৎ চলে গেছে"
        detail = (
            "বিদ্যুৎ সংযোগ এখন স্বাভাবিক।"
            if is_on
            else "বর্তমানে বিদ্যুৎ সংযোগ নেই।"
        )
        location_label = "স্থান"
        source_label = "উৎস"
    else:
        headline = "Electricity Restored" if is_on else "Power Outage"
        detail = (
            "Mains power is available again."
            if is_on
            else "Mains power is unavailable."
        )
        location_label = "Location"
        source_label = "Source"
    date_text, time_text = format_telegram_time(
        event, settings.timezone, settings.notification_language
    )
    return (
        f"{icon} {headline}\n\n"
        f"📍 {location_label}: {settings.site_name}\n"
        f"📅 {date_text}\n"
        f"🕐 {time_text}\n"
        f"🔌 {source_label}: {event.source}\n\n"
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
