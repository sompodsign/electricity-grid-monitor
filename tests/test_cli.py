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


if __name__ == "__main__":
    unittest.main()
