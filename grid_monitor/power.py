from __future__ import annotations

from pathlib import Path

from .models import PowerState


class PowerReadError(RuntimeError):
    pass


def discover_power_supply(root: Path = Path("/sys/class/power_supply")) -> Path:
    if not root.exists():
        raise PowerReadError(f"Power supply directory does not exist: {root}")

    candidates: list[Path] = []
    for item in sorted(root.iterdir()):
        type_file = item / "type"
        online_file = item / "online"
        try:
            supply_type = type_file.read_text(encoding="ascii").strip().lower()
        except OSError:
            continue
        if supply_type in {"mains", "usb", "usb_c"} and online_file.is_file():
            candidates.append(item)

    mains = [path for path in candidates if (path / "type").read_text().strip().lower() == "mains"]
    if mains:
        return mains[0]
    if candidates:
        return candidates[0]
    raise PowerReadError(f"No mains-compatible power supply found under {root}")


def read_power_state(supply_path: Path) -> PowerState:
    online_file = supply_path / "online" if supply_path.is_dir() else supply_path
    try:
        value = online_file.read_text(encoding="ascii").strip()
    except OSError as exc:
        raise PowerReadError(f"Cannot read power state from {online_file}: {exc}") from exc
    if value == "1":
        return PowerState.ON
    if value == "0":
        return PowerState.OFF
    raise PowerReadError(f"Unexpected value in {online_file}: {value!r}")

