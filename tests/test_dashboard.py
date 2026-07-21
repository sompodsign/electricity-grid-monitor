import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from grid_monitor.dashboard import (
    authorization_valid,
    create_session_token,
    csv_response,
    outage_pattern,
    notification_token,
    render_dashboard,
    session_cookie,
    session_valid,
    timeline_svg,
)
from grid_monitor.models import PowerEvent, PowerState
from grid_monitor.storage import EventStore


class DashboardTests(unittest.TestCase):
    def test_basic_authorization(self) -> None:
        import base64

        valid = base64.b64encode(b"reporter:test-password").decode("ascii")
        self.assertTrue(authorization_valid(f"Basic {valid}", "reporter", "test-password"))
        self.assertFalse(authorization_valid("Basic invalid", "reporter", "test-password"))
        self.assertFalse(authorization_valid(None, "reporter", "test-password"))

    def test_signed_session_cookie_expires_and_rejects_tampering(self) -> None:
        token = create_session_token("reporter", "test-password", now=1_000)
        cookie = f"grid_session={token}"

        self.assertTrue(session_valid(cookie, "reporter", "test-password", now=1_001))
        self.assertFalse(session_valid(cookie, "reporter", "wrong-password", now=1_001))
        self.assertFalse(session_valid(cookie, "reporter", "test-password", now=3_000_000))

        persistent = session_cookie(
            "reporter", "test-password", secure=True, now=1_000
        )
        self.assertIn("Max-Age=2592000", persistent)
        self.assertIn("Expires=Sat, 31 Jan 1970 00:16:40 GMT", persistent)
        self.assertIn("Secure", persistent)
        self.assertIn("Priority=High", persistent)

    def test_dashboard_renders_summary_events_and_escaped_site_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.db")
            store.initialize()
            now = datetime(2026, 1, 2, tzinfo=timezone.utc)
            store.add(PowerEvent(now - timedelta(hours=4), PowerState.ON, "AC", "initial"))
            store.add(PowerEvent(now - timedelta(hours=2), PowerState.OFF, "AC"))
            store.add(PowerEvent(now - timedelta(hours=1), PowerState.ON, "AC"))

            page = render_dashboard(
                store,
                "Home <Grid>",
                "24h",
                "UTC",
                now,
                Path(directory),
                notification_enabled=True,
                notification_csrf_token="test-token",
            )

            self.assertIn("Home &lt;Grid&gt;", page)
            self.assertIn("75.00%", page)
            self.assertIn("Outage", page)
            self.assertIn("/events.csv?period=24h", page)
            self.assertIn("Outage pattern by day and hour", page)
            self.assertIn('<strong class="status-duration">1h 0m</strong>', page)
            self.assertIn("Since Jan 01, 2026 23:00 UTC", page)
            self.assertIn("<th>Duration</th>", page)
            self.assertIn('<td class="duration">1h 0m</td>', page)
            self.assertIn("Notifications on", page)
            self.assertIn('name="enabled" value="off"', page)
            self.assertIn('name="token" value="test-token"', page)

    def test_notification_token_depends_on_dashboard_credentials(self) -> None:
        self.assertEqual(
            notification_token("reporter", "secret"),
            notification_token("reporter", "secret"),
        )
        self.assertNotEqual(
            notification_token("reporter", "secret"),
            notification_token("reporter", "different"),
        )

    def test_dashboard_defaults_invalid_period_to_24_hours(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.db")
            store.initialize()

            page = render_dashboard(
                store,
                "Home Grid",
                "invalid",
                "UTC",
                datetime(2026, 1, 2, tzinfo=timezone.utc),
                Path(directory),
            )

            self.assertIn('class="period active" href="/?period=24h"', page)
            self.assertIn('/events.csv?period=24h', page)

    def test_dashboard_contains_mobile_overflow_guards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.db")
            store.initialize()
            page = render_dashboard(
                store,
                "Home Grid",
                "24h",
                "UTC",
                datetime(2026, 1, 2, tzinfo=timezone.utc),
                Path(directory),
            )

            self.assertIn(
                "html,body { max-width:100%; overflow-x:hidden; overflow-x:clip; }",
                page,
            )
            self.assertIn(".toolbar,.section-head { flex-wrap:wrap; }", page)
            self.assertIn(
                '.server-status[open] .server-summary::after { content:"Hide details"; }',
                page,
            )
            self.assertIn(
                ".battery-packs { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); }",
                page,
            )
            self.assertIn(".heatmap-wrap,.table-wrap { overflow-x:hidden; }", page)
            self.assertIn(".heatmap { min-width:0; border-spacing:1px; }", page)
            self.assertIn(
                ".table-wrap th:nth-child(n+4),.table-wrap td:nth-child(n+4) { display:none; }",
                page,
            )
            self.assertIn(".heatmap-wrap { overflow-x:auto;", page)
            self.assertIn(".table-wrap { overflow-x:auto;", page)

    def test_csv_response_contains_period_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.db")
            store.initialize()
            now = datetime(2026, 1, 2, tzinfo=timezone.utc)
            store.add(PowerEvent(now - timedelta(hours=1), PowerState.OFF, "AC"))

            result = csv_response(store, "24h", now).decode("utf-8")

            self.assertIn("id,timestamp,state,source,reason", result)
            self.assertIn(",off,AC,transition", result)

    def test_event_history_marks_active_outage_duration_as_ongoing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.db")
            store.initialize()
            now = datetime(2026, 1, 2, tzinfo=timezone.utc)
            store.add(PowerEvent(now - timedelta(minutes=35), PowerState.OFF, "AC"))

            page = render_dashboard(
                store, "Home Grid", "24h", "UTC", now, Path(directory)
            )

            self.assertIn('<td class="duration">35m ongoing</td>', page)

    def test_empty_timeline_has_clear_state(self) -> None:
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        self.assertIn("No observations", timeline_svg([], now - timedelta(days=1), now))

    def test_outage_pattern_groups_by_weekday_and_hour(self) -> None:
        start = datetime(2026, 1, 5, 8, tzinfo=timezone.utc)  # Monday
        end = start + timedelta(hours=2)
        events = [
            PowerEvent(start, PowerState.ON, "AC", "initial"),
            PowerEvent(start + timedelta(minutes=30), PowerState.OFF, "AC"),
            PowerEvent(start + timedelta(hours=1, minutes=30), PowerState.ON, "AC"),
        ]

        result = outage_pattern(events, start, end, timezone.utc)

        self.assertEqual(result[0][8], (50.0, 3600.0))
        self.assertEqual(result[0][9], (50.0, 3600.0))
        self.assertIsNone(result[1][8])


if __name__ == "__main__":
    unittest.main()
