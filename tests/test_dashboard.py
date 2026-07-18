import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from grid_monitor.dashboard import csv_response, render_dashboard, timeline_svg
from grid_monitor.models import PowerEvent, PowerState
from grid_monitor.storage import EventStore


class DashboardTests(unittest.TestCase):
    def test_dashboard_renders_summary_events_and_escaped_site_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.db")
            store.initialize()
            now = datetime(2026, 1, 2, tzinfo=timezone.utc)
            store.add(PowerEvent(now - timedelta(hours=4), PowerState.ON, "AC", "initial"))
            store.add(PowerEvent(now - timedelta(hours=2), PowerState.OFF, "AC"))
            store.add(PowerEvent(now - timedelta(hours=1), PowerState.ON, "AC"))

            page = render_dashboard(store, "Home <Grid>", "24h", "UTC", now)

            self.assertIn("Home &lt;Grid&gt;", page)
            self.assertIn("75.00%", page)
            self.assertIn("Outage", page)
            self.assertIn("/events.csv?period=24h", page)

    def test_csv_response_contains_period_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.db")
            store.initialize()
            now = datetime(2026, 1, 2, tzinfo=timezone.utc)
            store.add(PowerEvent(now - timedelta(hours=1), PowerState.OFF, "AC"))

            result = csv_response(store, "24h", now).decode("utf-8")

            self.assertIn("id,timestamp,state,source,reason", result)
            self.assertIn(",off,AC,transition", result)

    def test_empty_timeline_has_clear_state(self) -> None:
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        self.assertIn("No observations", timeline_svg([], now - timedelta(days=1), now))


if __name__ == "__main__":
    unittest.main()
