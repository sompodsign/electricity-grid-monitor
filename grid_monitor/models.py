from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PowerState(str, Enum):
    ON = "on"
    OFF = "off"

    @property
    def label(self) -> str:
        return "Electricity Restored" if self is PowerState.ON else "Power Outage"


@dataclass(frozen=True)
class PowerEvent:
    timestamp: datetime
    state: PowerState
    source: str
    reason: str = "transition"
    event_id: int | None = None

