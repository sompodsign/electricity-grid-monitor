import tempfile
import unittest
from pathlib import Path

from grid_monitor.models import PowerState
from grid_monitor.power import discover_power_supply, read_power_state


class PowerTests(unittest.TestCase):
    def test_discovers_mains_before_usb(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, supply_type, online in [("USB0", "USB", "1"), ("AC", "Mains", "0")]:
                supply = root / name
                supply.mkdir()
                (supply / "type").write_text(supply_type, encoding="ascii")
                (supply / "online").write_text(online, encoding="ascii")
            selected = discover_power_supply(root)
            self.assertEqual(selected.name, "AC")
            self.assertIs(read_power_state(selected), PowerState.OFF)

    def test_reads_online_file_directly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            online = Path(directory) / "online"
            online.write_text("1\n", encoding="ascii")
            self.assertIs(read_power_state(online), PowerState.ON)


if __name__ == "__main__":
    unittest.main()

