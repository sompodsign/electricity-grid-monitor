import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from grid_monitor.cli import main


class CliTests(unittest.TestCase):
    def test_test_email_reports_disabled_flag_without_command_routing_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("NOTIFICATION_ENABLED=false\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                result = main(["--env-file", str(env_file), "test-email"])
            self.assertEqual(result, 1)

    def test_test_telegram_sends_sample_message(self) -> None:
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
            with patch.dict(os.environ, {}, clear=True), patch(
                "grid_monitor.cli.send_telegram_notification"
            ) as sender:
                result = main(["--env-file", str(env_file), "test-telegram"])
            self.assertEqual(result, 0)
            sender.assert_called_once()


if __name__ == "__main__":
    unittest.main()
