from __future__ import annotations

import logging

from .config import Settings
from .emailer import send_notification as send_email_notification
from .models import PowerEvent
from .telegram import send_telegram_notification


LOGGER = logging.getLogger(__name__)


def send_notifications(event: PowerEvent, settings: Settings) -> None:
    attempted = 0
    delivered = 0

    if settings.email_notification_enabled:
        attempted += 1
        try:
            send_email_notification(event, settings)
            delivered += 1
            LOGGER.info("Email notification sent to %s", settings.notification_to_email)
        except Exception:
            LOGGER.exception("Email notification delivery failed")

    if settings.telegram_enabled:
        attempted += 1
        try:
            send_telegram_notification(event, settings)
            delivered += 1
            LOGGER.info("Telegram notification sent")
        except Exception:
            LOGGER.exception("Telegram notification delivery failed")

    if attempted == 0:
        raise RuntimeError("No notification delivery channel is enabled")
    if delivered == 0:
        raise RuntimeError("All notification delivery channels failed")
