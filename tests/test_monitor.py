import tempfile
import unittest
from pathlib import Path

from grid_monitor.models import PowerState
from grid_monitor.monitor import GridMonitor

from .helpers import settings


class MonitorTests(unittest.TestCase):
    def test_records_only_initial_state_and_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            states = iter([PowerState.ON, PowerState.ON, PowerState.OFF])
            config = settings(Path(directory) / "events.db")
            monitor = GridMonitor(config, state_reader=lambda _path: next(states))
            monitor.store.initialize()

            first = monitor.check_once()
            duplicate = monitor.check_once()
            outage = monitor.check_once()

            self.assertEqual(first.reason, "initial")  # type: ignore[union-attr]
            self.assertIsNone(duplicate)
            self.assertIs(outage.state, PowerState.OFF)  # type: ignore[union-attr]
            self.assertEqual(len(monitor.store.list_events()), 2)

    def test_notification_flag_controls_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sent = []
            states = iter([PowerState.ON, PowerState.OFF])
            config = settings(
                Path(directory) / "events.db",
                notification_enabled=True,
                smtp_host="smtp.example.com",
                smtp_from_email="sender@example.com",
                notification_to_email="recipient@example.com",
            )
            monitor = GridMonitor(
                config,
                state_reader=lambda _path: next(states),
                notifier=lambda event, _settings: sent.append(event),
            )
            monitor.store.initialize()
            monitor.check_once()
            monitor.check_once()
            self.assertEqual([event.state for event in sent], [PowerState.OFF])


if __name__ == "__main__":
    unittest.main()

