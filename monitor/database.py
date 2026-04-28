"""SQLite database interface for storing OWL Intuition power readings."""

import sqlite3 as sl
from datetime import date, datetime, timezone


class Database:
    """Manages the SQLite database used to persist power readings."""

    def __init__(self, db_file_name: str) -> None:
        """Open (or create) the SQLite database and ensure the table exists.

        Args:
            db_file_name: Path to the SQLite file, or ':memory:' for tests.
        """
        self.connection = sl.connect(db_file_name)
        self.__create_table()

    def __create_table(self) -> None:
        """Create the PH_DATA table if it does not already exist."""
        with self.connection:
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS PH_DATA (
                    ID INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    UNIX_TIMESTAMP INTEGER,
                    TIMESTAMP TEXT,
                    WATTS REAL,
                    PUMP_ON INTEGER,
                    DURATION REAL
                );
            """)

    def insert_reading(self, unix_ts: int, ts: str, watts: float, pump_on: bool, duration: float) -> None:
        """Insert a single power reading into the database.

        Args:
            unix_ts: Reading time as a Unix timestamp.
            ts: Reading time formatted as 'YYYY-MM-DD HH:MM:SS' (UTC).
            watts: Measured power in watts.
            pump_on: True if the pump was drawing more than 1000 W.
            duration: Minutes elapsed since the last pump state change.
        """
        sql = 'INSERT INTO PH_DATA (UNIX_TIMESTAMP, TIMESTAMP, WATTS, PUMP_ON, DURATION) VALUES (?, ?, ?, ?, ?)'
        with self.connection:
            self.connection.execute(sql, (unix_ts, ts, watts, 1 if pump_on else 0, duration))

    def get_last_run_date_in_window(self, start_hour: int, end_hour: int,
                                    min_duration: float) -> date | None:
        """Return the most recent UTC date on which a qualifying run ended in the given hour window.

        Only counts ON→OFF transitions (the row where the pump first goes to PUMP_ON=0 after
        being on). At that row, DURATION equals the actual run length. Subsequent off-state
        rows have a growing "time since off" duration and are excluded by the LAG filter.

        Searches the last 30 days, which is sufficient to seed any cycle up to 14 nights.

        Args:
            start_hour: UTC hour window start (inclusive).
            end_hour: UTC hour window end (exclusive).
            min_duration: Minimum run duration in minutes.

        Returns:
            The most recent date, or None if no qualifying run exists.
        """
        cur = self.connection.execute(
            """
            SELECT MAX(UNIX_TIMESTAMP)
            FROM (
                SELECT UNIX_TIMESTAMP, TIMESTAMP, DURATION, PUMP_ON,
                       LAG(PUMP_ON, 1, 0) OVER (ORDER BY UNIX_TIMESTAMP) AS prev_pump_on
                FROM PH_DATA
                WHERE UNIX_TIMESTAMP >= (SELECT MAX(UNIX_TIMESTAMP) FROM PH_DATA) - 30 * 86400
            )
            WHERE PUMP_ON = 0
              AND prev_pump_on = 1
              AND DURATION >= ?
              AND CAST(strftime('%H', TIMESTAMP) AS INTEGER) >= ?
              AND CAST(strftime('%H', TIMESTAMP) AS INTEGER) < ?
            """,
            (min_duration, start_hour, end_hour),
        )
        row = cur.fetchone()
        if row[0] is None:
            return None
        return datetime.fromtimestamp(row[0], tz=timezone.utc).date()

    def get_runs_between(self, start_ts: int, end_ts: int,
                         min_duration: float = 3.0) -> list[tuple[int, float]]:
        """Return completed pump runs (ON→OFF transitions) above a minimum duration.

        Each returned row is the moment the pump turned off; DURATION at that point equals
        the actual run length. Uses LAG to exclude the continuous stream of off-state readings
        that follow each transition. Filters out brief micro-cycles below min_duration.

        Args:
            start_ts: Range start as Unix timestamp (inclusive).
            end_ts: Range end as Unix timestamp (exclusive).
            min_duration: Minimum run length in minutes to include (default: 3).

        Returns:
            List of (unix_timestamp, duration_minutes) tuples ordered by timestamp.
        """
        cur = self.connection.execute(
            """
            SELECT UNIX_TIMESTAMP, DURATION
            FROM (
                SELECT UNIX_TIMESTAMP, DURATION, PUMP_ON,
                       LAG(PUMP_ON, 1, 0) OVER (ORDER BY UNIX_TIMESTAMP) AS prev_pump_on
                FROM PH_DATA
                WHERE UNIX_TIMESTAMP >= ? AND UNIX_TIMESTAMP < ?
            )
            WHERE PUMP_ON = 0 AND prev_pump_on = 1 AND DURATION >= ?
            ORDER BY UNIX_TIMESTAMP
            """,
            (start_ts, end_ts, min_duration),
        )
        return cur.fetchall()
