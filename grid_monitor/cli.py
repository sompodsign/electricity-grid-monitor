from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .dashboard import serve_dashboard
from .emailer import send_notification
from .models import PowerEvent, PowerState
from .monitor import GridMonitor, run_until_signal
from .power import discover_power_supply, read_power_state
from .reporting import export_csv, parse_period, plot_events, summarize
from .storage import EventStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="grid-monitor",
        description="Log mains electricity changes and report grid availability.",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="configuration file")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("monitor", help="run the continuous electricity monitor")
    commands.add_parser("check", help="check once and log a transition if needed")
    commands.add_parser("status", help="show live and last-recorded status")

    history = commands.add_parser("history", help="show recent transition history")
    history.add_argument("--limit", type=positive_int, default=20)

    summary = commands.add_parser("summary", help="show availability statistics")
    summary.add_argument("--period", default="7d", help="period such as 24h, 7d, or 4w")

    plot = commands.add_parser("plot", help="create a PNG report")
    plot.add_argument("--period", default="7d", help="period such as 24h, 7d, or 4w")
    plot.add_argument("--output", type=Path, default=Path("reports/grid-status.png"))

    export = commands.add_parser("export", help="export events to CSV")
    export.add_argument("--period", default="30d", help="period such as 24h, 7d, or 4w")
    export.add_argument("--output", type=Path, default=Path("reports/grid-events.csv"))

    serve = commands.add_parser("serve", help="serve the local reporting dashboard")
    serve.add_argument("--host", default="127.0.0.1", help="interface to bind (default: localhost)")
    serve.add_argument("--port", type=port_number, default=8090)

    commands.add_parser("test-email", help="send a sample notification using SMTP settings")
    return parser


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def port_number(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= 65535:
        raise argparse.ArgumentTypeError("must be between 1 and 65535")
    return parsed


def format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    days, total = divmod(total, 86400)
    hours, total = divmod(total, 3600)
    minutes, secs = divmod(total, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def initialize_store(settings: Settings) -> EventStore:
    store = EventStore(settings.database_path)
    store.initialize()
    return store


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        settings = Settings.from_env(args.env_file)
        return run_command(args, settings)
    except (OSError, RuntimeError, ValueError) as exc:
        logging.error("%s", exc)
        return 1


def run_command(args: argparse.Namespace, settings: Settings) -> int:
    if args.command in {"monitor", "check"}:
        monitor = GridMonitor(settings)
        monitor.store.initialize()
        if args.command == "monitor":
            run_until_signal(monitor)
        else:
            event = monitor.check_once()
            print(
                f"Recorded {event.state.value.upper()} at {event.timestamp.isoformat()}"
                if event
                else "No state change"
            )
        return 0

    store = initialize_store(settings)
    if args.command == "status":
        supply = settings.power_supply_path or discover_power_supply()
        live = read_power_state(supply)
        latest = store.latest()
        print(f"Live mains power: {live.value.upper()} ({supply})")
        print(f"Notifications: {'ENABLED' if settings.notification_enabled else 'DISABLED'}")
        if latest:
            print(f"Last event: {latest.state.value.upper()} at {latest.timestamp.isoformat()}")
        else:
            print("Last event: no observations recorded")
        return 0

    if args.command == "history":
        events = store.list_events(limit=args.limit, descending=True)
        if not events:
            print("No events recorded")
            return 0
        print(f"{'TIMESTAMP':<33} {'STATE':<7} {'REASON':<10} SOURCE")
        for event in events:
            print(
                f"{event.timestamp.isoformat():<33} {event.state.value.upper():<7} "
                f"{event.reason:<10} {event.source}"
            )
        return 0

    if args.command == "test-email":
        if not settings.notification_enabled:
            raise ValueError("Set NOTIFICATION_ENABLED=true before testing email")
        event = PowerEvent(datetime.now(timezone.utc), PowerState.ON, "test", "transition")
        send_notification(event, settings)
        print(f"Test email sent to {settings.notification_to_email}")
        return 0

    if args.command == "serve":
        serve_dashboard(
            store,
            settings.site_name,
            settings.timezone,
            args.host,
            args.port,
            settings.dashboard_username,
            settings.dashboard_password,
            settings.battery_warning_percent,
        )
        return 0

    start, end = parse_period(args.period)
    if args.command == "summary":
        result = summarize(store, start, end)
        print(f"Observed: {format_duration(result.observed_seconds)}")
        print(f"Availability: {result.availability_percent:.3f}%")
        print(f"Power available: {format_duration(result.online_seconds)}")
        print(f"Power unavailable: {format_duration(result.outage_seconds)}")
        print(f"Outages detected: {result.outage_count}")
        print(f"Current recorded state: {result.current_state.value.upper() if result.current_state else 'UNKNOWN'}")
        return 0

    if args.command == "plot":
        plot_events(store, start, end, args.output, settings.site_name)
        print(f"Plot written to {args.output.resolve()}")
        return 0

    if args.command == "export":
        events = store.list_events(start=start, end=end)
        export_csv(events, args.output)
        print(f"Exported {len(events)} events to {args.output.resolve()}")
        return 0

    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
