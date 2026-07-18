from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class BatteryPack:
    name: str
    status: str
    percent: float | None
    energy_now_wh: float | None
    energy_full_wh: float | None
    energy_design_wh: float | None
    power_w: float | None

    @property
    def health_percent(self) -> float | None:
        if not self.energy_full_wh or not self.energy_design_wh:
            return None
        return min(100.0, self.energy_full_wh / self.energy_design_wh * 100)


@dataclass(frozen=True)
class BatteryTelemetry:
    packs: tuple[BatteryPack, ...]
    percent: float | None
    energy_now_wh: float
    power_w: float
    runtime_seconds: float | None
    cutoff_at: datetime | None
    discharging: bool


def _read_number(path: Path) -> float | None:
    try:
        return float(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None


def _read_text(path: Path, default: str = "Unknown") -> str:
    try:
        return path.read_text(encoding="ascii").strip() or default
    except OSError:
        return default


def _energy_wh(directory: Path, energy_name: str, charge_name: str) -> float | None:
    energy = _read_number(directory / energy_name)
    if energy is not None:
        return energy / 1_000_000
    charge = _read_number(directory / charge_name)
    voltage = _read_number(directory / "voltage_now")
    if charge is None or voltage is None:
        return None
    return charge * voltage / 1_000_000_000_000


def _power_w(directory: Path) -> float | None:
    power = _read_number(directory / "power_now")
    if power is not None:
        return power / 1_000_000
    current = _read_number(directory / "current_now")
    voltage = _read_number(directory / "voltage_now")
    if current is None or voltage is None:
        return None
    return current * voltage / 1_000_000_000_000


def read_battery_telemetry(
    root: Path = Path("/sys/class/power_supply"),
    now: datetime | None = None,
) -> BatteryTelemetry | None:
    packs = []
    for directory in sorted(root.glob("BAT*")):
        present = _read_number(directory / "present")
        if present == 0:
            continue
        capacity = _read_number(directory / "capacity")
        packs.append(
            BatteryPack(
                name=directory.name,
                status=_read_text(directory / "status"),
                percent=capacity,
                energy_now_wh=_energy_wh(directory, "energy_now", "charge_now"),
                energy_full_wh=_energy_wh(directory, "energy_full", "charge_full"),
                energy_design_wh=_energy_wh(
                    directory, "energy_full_design", "charge_full_design"
                ),
                power_w=_power_w(directory),
            )
        )
    if not packs:
        return None

    energy_now = sum(pack.energy_now_wh or 0 for pack in packs)
    energy_full = sum(pack.energy_full_wh or 0 for pack in packs)
    percent = energy_now / energy_full * 100 if energy_full else None
    discharging = any(pack.status.lower() == "discharging" for pack in packs)
    power = sum(pack.power_w or 0 for pack in packs if pack.status.lower() == "discharging")
    runtime = energy_now / power * 3600 if discharging and power > 0 else None
    cutoff = now + timedelta(seconds=runtime) if now is not None and runtime is not None else None
    return BatteryTelemetry(tuple(packs), percent, energy_now, power, runtime, cutoff, discharging)
