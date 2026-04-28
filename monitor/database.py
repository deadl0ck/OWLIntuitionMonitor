"""SQLite database interface for storing OWL Intuition power readings."""

import sqlite3 as sl


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
