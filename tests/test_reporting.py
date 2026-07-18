import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from grid_monitor.models import PowerEvent, PowerState
from grid_monitor.reporting import parse_period, summarize
from grid_monitor.storage import EventStore


class ReportingTests(unittest.TestCase):
    def test_summary_calculates_availability_and_outages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.db")
            store.initialize()
            start = datetime(2026, 1, 1, tzinfo=timezone.utc)
            store.add(PowerEvent(start, PowerState.ON, "AC", "initial"))
            store.add(PowerEvent(start + timedelta(hours=2), PowerState.OFF, "AC"))
            store.add(PowerEvent(start + timedelta(hours=3), PowerState.ON, "AC"))

            result = summarize(store, start, start + timedelta(hours=4))
            self.assertEqual(result.outage_count, 1)
            self.assertEqual(result.online_seconds, 3 * 3600)
            self.assertEqual(result.outage_seconds, 3600)
            self.assertEqual(result.availability_percent, 75.0)

    def test_parse_period(self) -> None:
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        start, end = parse_period("24h", now)
        self.assertEqual(end - start, timedelta(days=1))


if __name__ == "__main__":
    unittest.main()
