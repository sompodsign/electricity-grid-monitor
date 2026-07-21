import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from grid_monitor.models import PowerEvent, PowerState
from grid_monitor.notifier import send_notifications
from grid_monitor.telegram import build_telegram_text, send_telegram_notification

from .helpers import settings


class FakeResponse:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class TelegramTests(unittest.TestCase):
    def test_message_describes_outage(self) -> None:
        config = settings(Path("events.db"))
        event = PowerEvent(
            datetime(2026, 7, 21, 12, 30, tzinfo=timezone.utc),
            PowerState.OFF,
            "AC",
        )

        message = build_telegram_text(event, config)

        self.assertIn("Power Outage", message)
        self.assertIn("📍 Location: Test Grid", message)
        self.assertIn("📅 Tuesday, 21 July 2026", message)
        self.assertIn("🕐 12:30:00 PM (UTC+00:00)", message)
        self.assertIn("Source: AC", message)

    def test_message_can_render_in_bengali(self) -> None:
        config = settings(
            Path("events.db"), timezone="Asia/Dhaka", notification_language="bn"
        )
        event = PowerEvent(
            datetime(2026, 7, 21, 19, 57, 52, tzinfo=timezone.utc),
            PowerState.ON,
            "AC",
        )

        message = build_telegram_text(event, config)

        self.assertIn("বিদ্যুৎ ফিরে এসেছে", message)
        self.assertIn("বুধবার, ২২ জুলাই ২০২৬", message)
        self.assertIn("রাত ১:৫৭:৫২ (UTC+06:00)", message)

    def test_sender_posts_message_to_bot_api(self) -> None:
        config = settings(
            Path("events.db"),
            telegram_enabled=True,
            telegram_bot_token="secret-token",
            telegram_chat_id="12345",
        )
        event = PowerEvent(datetime.now(timezone.utc), PowerState.ON, "AC")

        with patch(
            "grid_monitor.telegram.urlopen", return_value=FakeResponse({"ok": True})
        ) as mocked_urlopen:
            send_telegram_notification(event, config)

        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertTrue(request.full_url.endswith("/sendMessage"))
        self.assertEqual(payload["chat_id"], "12345")
        self.assertIn("Electricity Restored", payload["text"])

    def test_channel_failure_does_not_block_another_channel(self) -> None:
        config = settings(
            Path("events.db"),
            email_notification_enabled=True,
            telegram_enabled=True,
        )
        event = PowerEvent(datetime.now(timezone.utc), PowerState.OFF, "AC")

        with patch(
            "grid_monitor.notifier.send_email_notification",
            side_effect=RuntimeError("email failed"),
        ) as email_sender, patch(
            "grid_monitor.notifier.send_telegram_notification"
        ) as telegram_sender:
            send_notifications(event, config)

        email_sender.assert_called_once_with(event, config)
        telegram_sender.assert_called_once_with(event, config)


if __name__ == "__main__":
    unittest.main()
