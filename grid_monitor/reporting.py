from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import PowerEvent, PowerState
from .storage import EventStore


@dataclass(frozen=True)
class GridSummary:
    start: datetime
    end: datetime
    observed_seconds: float
    online_seconds: float
    outage_seconds: float
    outage_count: int
    current_state: PowerState | None

    @property
    def availability_percent(self) -> float:
        if self.observed_seconds <= 0:
            return 0.0
        return self.online_seconds / self.observed_seconds * 100


def parse_period(period: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(timezone.utc)
    units = {"h": "hours", "d": "days", "w": "weeks"}
    if len(period) < 2 or period[-1].lower() not in units:
        raise ValueError("Period must use h, d, or w, for example: 24h, 7d, 4w")
    try:
        amount = float(period[:-1])
    except ValueError as exc:
        raise ValueError("Period must use h, d, or w, for example: 24h, 7d, 4w") from exc
    if amount <= 0:
        raise ValueError("Period must be greater than zero")
    return now - timedelta(**{units[period[-1].lower()]: amount}), now


def events_with_context(store: EventStore, start: datetime, end: datetime) -> list[PowerEvent]:
    events = store.list_events(start=start, end=end)
    before = store.state_before(start)
    if before:
        context = PowerEvent(start, before.state, before.source, before.reason, before.event_id)
        return [context, *events]
    return events


def summarize(store: EventStore, start: datetime, end: datetime) -> GridSummary:
    events = events_with_context(store, start, end)
    if not events:
        return GridSummary(start, end, 0, 0, 0, 0, None)

    effective_start = max(start, events[0].timestamp)
    online_seconds = 0.0
    outage_seconds = 0.0
    outage_count = sum(
        event.state is PowerState.OFF and event.reason == "transition"
        for event in events
        if start <= event.timestamp <= end
    )
    for index, event in enumerate(events):
        segment_start = max(effective_start, event.timestamp)
        segment_end = events[index + 1].timestamp if index + 1 < len(events) else end
        segment_end = min(segment_end, end)
        seconds = max(0.0, (segment_end - segment_start).total_seconds())
        if event.state is PowerState.ON:
            online_seconds += seconds
        else:
            outage_seconds += seconds
    return GridSummary(
        start=effective_start,
        end=end,
        observed_seconds=max(0.0, (end - effective_start).total_seconds()),
        online_seconds=online_seconds,
        outage_seconds=outage_seconds,
        outage_count=outage_count,
        current_state=events[-1].state,
    )


def export_csv(events: list[PowerEvent], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["id", "timestamp", "state", "source", "reason"])
        for event in events:
            writer.writerow(
                [event.event_id, event.timestamp.isoformat(), event.state.value, event.source, event.reason]
            )


def plot_events(
    store: EventStore,
    start: datetime,
    end: datetime,
    output_path: Path,
    site_name: str,
) -> None:
    try:
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("Plotting requires Matplotlib: pip install -e '.[plot]'") from exc

    events = events_with_context(store, start, end)
    if not events:
        raise ValueError("No observations are available in the selected period")

    times = [event.timestamp for event in events]
    values = [1 if event.state is PowerState.ON else 0 for event in events]
    times.append(end)
    values.append(values[-1])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, (timeline, daily) = plt.subplots(
        2, 1, figsize=(12, 7), gridspec_kw={"height_ratios": [2, 3]}, constrained_layout=True
    )
    timeline.step(times, values, where="post", color="#176b52", linewidth=2)
    timeline.fill_between(times, values, step="post", color="#55b98a", alpha=0.25)
    timeline.set_yticks([0, 1], labels=["Outage", "Available"])
    timeline.set_ylim(-0.15, 1.15)
    timeline.set_title(f"{site_name} - Electricity Status")
    timeline.grid(axis="x", alpha=0.2)
    timeline.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))

    daily_labels: list[str] = []
    daily_values: list[float] = []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < end:
        day_end = min(day + timedelta(days=1), end)
        day_start = max(day, start)
        summary = summarize(store, day_start, day_end)
        if summary.observed_seconds:
            daily_labels.append(day_start.strftime("%b %d"))
            daily_values.append(summary.availability_percent)
        day += timedelta(days=1)
    daily.bar(daily_labels, daily_values, color="#277da1", width=0.72)
    daily.set_ylim(0, 100)
    daily.set_ylabel("Availability (%)")
    daily.set_title("Daily Availability")
    daily.grid(axis="y", alpha=0.2)
    daily.tick_params(axis="x", rotation=35)

    fig.savefig(output_path, dpi=160)
    plt.close(fig)
