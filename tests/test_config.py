import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from grid_monitor.config import Settings, env_bool


class ConfigTests(unittest.TestCase):
    def test_env_bool_accepts_common_values(self) -> None:
        with patch.dict(os.environ, {"FLAG": "yes"}, clear=False):
            self.assertTrue(env_bool("FLAG"))
        with patch.dict(os.environ, {"FLAG": "disabled"}, clear=False):
            self.assertFalse(env_bool("FLAG", True))

    def test_notifications_require_email_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("NOTIFICATION_ENABLED=true\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ValueError, "SMTP_HOST"):
                    Settings.from_env(env_file)

    def test_env_file_loads_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "POLL_INTERVAL_SECONDS=2.5\nSITE_NAME='Workshop Grid'\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                result = Settings.from_env(env_file)
            self.assertEqual(result.poll_interval_seconds, 2.5)
            self.assertEqual(result.site_name, "Workshop Grid")

    def test_telegram_can_be_the_only_delivery_channel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "NOTIFICATION_ENABLED=true\n"
                "EMAIL_NOTIFICATION_ENABLED=false\n"
                "TELEGRAM_ENABLED=true\n"
                "TELEGRAM_BOT_TOKEN=test-token\n"
                "TELEGRAM_CHAT_ID=12345\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                result = Settings.from_env(env_file)
            self.assertFalse(result.email_notification_enabled)
            self.assertTrue(result.telegram_enabled)

    def test_enabled_telegram_requires_chat_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "NOTIFICATION_ENABLED=true\n"
                "EMAIL_NOTIFICATION_ENABLED=false\n"
                "TELEGRAM_ENABLED=true\n"
                "TELEGRAM_BOT_TOKEN=test-token\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ValueError, "TELEGRAM_CHAT_ID"):
                    Settings.from_env(env_file)


if __name__ == "__main__":
    unittest.main()
