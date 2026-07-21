from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .models import PowerEvent, PowerState


class EventStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS power_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('on', 'off')),
                    source TEXT NOT NULL,
                    reason TEXT NOT NULL CHECK (reason IN ('initial', 'transition'))
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_power_events_timestamp "
                "ON power_events(timestamp)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS runtime_settings ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )

    def notification_enabled(self, default: bool) -> bool:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT value FROM runtime_settings WHERE key = 'notification_enabled'"
            ).fetchone()
        if row is None:
            return default
        return row["value"] == "true"

    def set_notification_enabled(self, enabled: bool) -> None:
        with closing(self.connect()) as connection, connection:
            connection.execute(
                "INSERT INTO runtime_settings(key, value) VALUES "
                "('notification_enabled', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("true" if enabled else "false",),
            )

    def notification_language(self, default: str) -> str:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT value FROM runtime_settings WHERE key = 'notification_language'"
            ).fetchone()
        if row is None or row["value"] not in {"en", "bn"}:
            return default
        return row["value"]

    def set_notification_language(self, language: str) -> None:
        if language not in {"en", "bn"}:
            raise ValueError("Notification language must be either en or bn")
        with closing(self.connect()) as connection, connection:
            connection.execute(
                "INSERT INTO runtime_settings(key, value) VALUES "
                "('notification_language', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (language,),
            )

    def add(self, event: PowerEvent) -> PowerEvent:
        with closing(self.connect()) as connection, connection:
            cursor = connection.execute(
                "INSERT INTO power_events(timestamp, state, source, reason) VALUES (?, ?, ?, ?)",
                (event.timestamp.isoformat(), event.state.value, event.source, event.reason),
            )
        return PowerEvent(
            timestamp=event.timestamp,
            state=event.state,
            source=event.source,
            reason=event.reason,
            event_id=cursor.lastrowid,
        )

    def latest(self) -> PowerEvent | None:
        with closing(self.connect()) as connection, connection:
            row = connection.execute(
                "SELECT * FROM power_events ORDER BY timestamp DESC, id DESC LIMIT 1"
            ).fetchone()
        return self._from_row(row) if row else None

    def list_events(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
        descending: bool = False,
    ) -> list[PowerEvent]:
        clauses: list[str] = []
        parameters: list[object] = []
        if start:
            clauses.append("timestamp >= ?")
            parameters.append(start.isoformat())
        if end:
            clauses.append("timestamp <= ?")
            parameters.append(end.isoformat())
        query = "SELECT * FROM power_events"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY timestamp " + ("DESC" if descending else "ASC") + ", id " + (
            "DESC" if descending else "ASC"
        )
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)
        with closing(self.connect()) as connection, connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._from_row(row) for row in rows]

    def state_before(self, timestamp: datetime) -> PowerEvent | None:
        with closing(self.connect()) as connection, connection:
            row = connection.execute(
                "SELECT * FROM power_events WHERE timestamp < ? "
                "ORDER BY timestamp DESC, id DESC LIMIT 1",
                (timestamp.isoformat(),),
            ).fetchone()
        return self._from_row(row) if row else None

    @staticmethod
    def _from_row(row: sqlite3.Row) -> PowerEvent:
        return PowerEvent(
            event_id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            state=PowerState(row["state"]),
            source=row["source"],
            reason=row["reason"],
        )
