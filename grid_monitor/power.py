from __future__ import annotations

import socket
import threading
from pathlib import Path
from time import monotonic

from .models import PowerState

NETLINK_KOBJECT_UEVENT = 15


class PowerReadError(RuntimeError):
    pass


class MainsStateReader:
    """Latch physical mains transitions hidden by an online USB-C backup."""

    def __init__(self, supply_path: Path, state_path: Path):
        self.supply_path = supply_path
        self.state_path = state_path
        self._lock = threading.Lock()
        self._state = self._load_state()
        self._last_direction_event = 0.0
        self._last_ac_event = 0.0
        self._listener = threading.Thread(
            target=self._listen_for_power_events,
            name="mains-power-events",
            daemon=True,
        )
        self._listener.start()

    def __call__(self, _supply_path: Path) -> PowerState:
        if not _usb_c_online(self.supply_path):
            state = read_power_state(self.supply_path)
            self._set_state(state)
            return state
        with self._lock:
            if self._state is not None:
                return self._state
        state = read_mains_state(self.supply_path)
        self._set_state(state)
        return state

    def _load_state(self) -> PowerState | None:
        try:
            return PowerState(self.state_path.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return None

    def _set_state(self, state: PowerState) -> None:
        with self._lock:
            if self._state is state:
                return
            self._state = state
            try:
                self.state_path.parent.mkdir(parents=True, exist_ok=True)
                self.state_path.write_text(state.value + "\n", encoding="ascii")
            except OSError:
                pass

    def _listen_for_power_events(self) -> None:
        try:
            listener = socket.socket(
                socket.AF_NETLINK, socket.SOCK_DGRAM, NETLINK_KOBJECT_UEVENT
            )
            listener.bind((0, 1))
        except OSError:
            return
        with listener:
            while True:
                try:
                    payload = listener.recv(16_384).decode("utf-8", errors="replace")
                except OSError:
                    return
                fields = {}
                for item in payload.split("\0"):
                    key, separator, value = item.partition("=")
                    if separator:
                        fields[key] = value
                if (
                    fields.get("SUBSYSTEM") != "power_supply"
                    or not _usb_c_online(self.supply_path)
                ):
                    continue
                now = monotonic()
                if fields.get("POWER_SUPPLY_TYPE") == "Battery":
                    status = fields.get("POWER_SUPPLY_STATUS", "").lower()
                    if status == "discharging":
                        self._last_direction_event = now
                        self._set_state(PowerState.OFF)
                    elif status == "charging":
                        self._last_direction_event = now
                        self._set_state(PowerState.ON)
                elif (
                    fields.get("POWER_SUPPLY_TYPE") == "Mains"
                    and fields.get("POWER_SUPPLY_NAME") == self.supply_path.name
                    and now - self._last_ac_event >= 1.0
                ):
                    self._last_ac_event = now
                    if now - self._last_direction_event >= 2.0:
                        statuses = _battery_statuses(self.supply_path)
                        if any(
                            status in {"charging", "full"} for status in statuses
                        ):
                            self._set_state(PowerState.ON)


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


def _power_supply_root(supply_path: Path) -> Path:
    supply_directory = supply_path if supply_path.is_dir() else supply_path.parent
    return supply_directory.parent


def _usb_c_online(supply_path: Path) -> bool:
    for directory in _power_supply_root(supply_path).iterdir():
        try:
            supply_type = (directory / "type").read_text(encoding="ascii").strip().lower()
            online = (directory / "online").read_text(encoding="ascii").strip()
        except OSError:
            continue
        if supply_type in {"usb", "usb_c"} and online == "1":
            return True
    return False


def _battery_statuses(supply_path: Path) -> list[str]:
    statuses = []
    for directory in sorted(_power_supply_root(supply_path).glob("BAT*")):
        try:
            present = (directory / "present").read_text(encoding="ascii").strip()
            status = (directory / "status").read_text(encoding="ascii").strip().lower()
        except OSError:
            continue
        if present != "0":
            statuses.append(status)
    return statuses


def read_mains_state(supply_path: Path) -> PowerState:
    """Read physical mains separately from USB-C backup on dual-input laptops.

    Some ThinkPads expose ACPI ``AC/online`` as an aggregate external-power flag.
    When USB-C PD is online, battery charging status provides the separate slim-tip
    signal: this T470s reports Charging/Full with mains and Not charging or
    Discharging after the main adapter is removed.
    """
    aggregate_state = read_power_state(supply_path)
    if aggregate_state is PowerState.OFF:
        return PowerState.OFF

    if not _usb_c_online(supply_path):
        return aggregate_state

    battery_statuses = _battery_statuses(supply_path)
    if any(status in {"charging", "full"} for status in battery_statuses):
        return PowerState.ON
    if battery_statuses and all(
        status in {"discharging", "not charging"} for status in battery_statuses
    ):
        return PowerState.OFF
    raise PowerReadError(
        "Cannot separate mains from USB-C backup; battery status is "
        + (", ".join(battery_statuses) if battery_statuses else "unavailable")
    )
