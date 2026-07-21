import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from grid_monitor.battery import read_battery_telemetry
from grid_monitor.dashboard import battery_panel


class BatteryTests(unittest.TestCase):
    def test_combines_packs_and_estimates_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_pack(root / "BAT0", 80, 16_000_000, 20_000_000, 4_000_000)
            self.write_pack(
                root / "BAT1", 0, 0, 5_000_000, 0, status="Not charging"
            )
            now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)

            result = read_battery_telemetry(root, now)

            self.assertIsNotNone(result)
            assert result is not None
            self.assertAlmostEqual(result.percent or 0, 64.0)
            self.assertEqual(result.runtime_seconds, 14_400)
            self.assertEqual(result.cutoff_at, datetime(2026, 1, 1, 16, tzinfo=timezone.utc))
            self.assertEqual(len(result.packs), 2)
            panel = battery_panel(result, timezone.utc, 15)
            self.assertTrue(panel.startswith('<details class="server-status">'))
            self.assertIn('<summary class="server-summary">', panel)
            self.assertNotIn("<details open", panel)
            self.assertIn("Server battery", panel)
            self.assertIn("4h 0m remaining", panel)
            self.assertIn("Estimated cutoff Jan 01, 2026 16:00 UTC", panel)
            self.assertIn("BAT1 0%", panel)

    @staticmethod
    def write_pack(
        directory: Path,
        capacity: int,
        energy_now: int,
        energy_full: int,
        power_now: int,
        status: str = "Discharging",
    ) -> None:
        directory.mkdir()
        values = {
            "present": "1",
            "capacity": str(capacity),
            "status": status,
            "energy_now": str(energy_now),
            "energy_full": str(energy_full),
            "energy_full_design": str(energy_full),
            "power_now": str(power_now),
        }
        for name, value in values.items():
            (directory / name).write_text(value, encoding="ascii")


if __name__ == "__main__":
    unittest.main()
