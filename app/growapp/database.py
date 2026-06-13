import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    channel INTEGER NOT NULL,
    saturation REAL NOT NULL,
    pulses REAL NOT NULL,
    active INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_readings_channel_ts ON readings (channel, ts);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    channel INTEGER,
    type TEXT NOT NULL,      -- watering | manual_watering | low_moisture | sensor_inactive | info
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events (ts);
"""


class Database:
    """Thread-safe SQLite wrapper (controller thread + web threads share it)."""

    def __init__(self, path):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def add_reading(self, channel, saturation, pulses, active, ts=None):
        with self._lock:
            self._conn.execute(
                "INSERT INTO readings (ts, channel, saturation, pulses, active) VALUES (?, ?, ?, ?, ?)",
                (ts or time.time(), channel, saturation, pulses, int(active)),
            )
            self._conn.commit()

    def add_event(self, type, channel=None, detail=None, ts=None):
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (ts, channel, type, detail) VALUES (?, ?, ?, ?)",
                (ts or time.time(), channel, type, detail),
            )
            self._conn.commit()

    def latest_readings(self):
        """Most recent reading per channel."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT r.* FROM readings r
                   JOIN (SELECT channel, MAX(ts) AS ts FROM readings GROUP BY channel) m
                     ON r.channel = m.channel AND r.ts = m.ts"""
            ).fetchall()
        return {row["channel"]: dict(row) for row in rows}

    def history(self, channel, hours=24, max_points=500):
        since = time.time() - hours * 3600
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, saturation FROM readings WHERE channel = ? AND ts >= ? ORDER BY ts",
                (channel, since),
            ).fetchall()
        # Downsample evenly so the chart payload stays small on a Pi Zero.
        if len(rows) > max_points:
            step = len(rows) / max_points
            rows = [rows[int(i * step)] for i in range(max_points)]
        return [{"ts": row["ts"], "saturation": row["saturation"]} for row in rows]

    def recent_events(self, limit=50):
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def waterings_since(self, channel, since_ts):
        with self._lock:
            row = self._conn.execute(
                """SELECT COUNT(*) AS n, MAX(ts) AS last FROM events
                   WHERE channel = ? AND ts >= ? AND type IN ('watering', 'manual_watering')""",
                (channel, since_ts),
            ).fetchone()
        return row["n"], row["last"]

    def prune(self, retention_days):
        cutoff = time.time() - retention_days * 86400
        with self._lock:
            self._conn.execute("DELETE FROM readings WHERE ts < ?", (cutoff,))
            self._conn.commit()
