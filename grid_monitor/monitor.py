from __future__ import annotations

import logging
import signal
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import Settings
from .emailer import send_notification
from .models import PowerEvent, PowerState
from .power import discover_power_supply, read_power_state
from .storage import EventStore

LOGGER = logging.getLogger(__name__)


class GridMonitor:
    def __init__(
        self,
        settings: Settings,
        *,
        state_reader: Callable[[Path], PowerState] = read_power_state,
        notifier: Callable[[PowerEvent, Settings], None] = send_notification,
    ):
        self.settings = settings
        self.store = EventStore(settings.database_path)
        self.supply_path = settings.power_supply_path or discover_power_supply()
        self.state_reader = state_reader
        self.notifier = notifier

    def check_once(self) -> PowerEvent | None:
        current_state = self.state_reader(self.supply_path)
        previous = self.store.latest()
        if previous and previous.state is current_state:
            return None

        event = PowerEvent(
            timestamp=datetime.now(timezone.utc),
            state=current_state,
            source=self.supply_path.name,
            reason="transition" if previous else "initial",
        )
        event = self.store.add(event)
        LOGGER.info("Recorded %s event from %s", event.state.value, event.source)

        notifications_enabled = self.store.notification_enabled(
            self.settings.notification_enabled
        )
        if notifications_enabled and event.reason == "transition":
            try:
                self.notifier(event, self.settings)
                LOGGER.info("Notification sent to %s", self.settings.notification_to_email)
            except Exception:
                LOGGER.exception("Could not send power notification")
        return event

    def run(self, stop_event: threading.Event | None = None) -> None:
        self.store.initialize()
        if stop_event is None:
            stop_event = threading.Event()
        LOGGER.info(
            "Monitoring %s every %.1f seconds; notifications are %s",
            self.supply_path,
            self.settings.poll_interval_seconds,
            "enabled" if self.settings.notification_enabled else "disabled",
        )
        while not stop_event.is_set():
            try:
                self.check_once()
            except Exception:
                LOGGER.exception("Power check failed")
            stop_event.wait(self.settings.poll_interval_seconds)


def run_until_signal(monitor: GridMonitor) -> None:
    stop_event = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        LOGGER.info("Stopping monitor")
        stop_event.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    monitor.run(stop_event)
