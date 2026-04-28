import sqlite3 as sl


class Database:
    def __init__(self, db_file_name: str):
        self.connection = sl.connect(db_file_name)
        self.__create_table()

    def __create_table(self):
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

    def insert_reading(self, unix_ts: int, ts: str, watts: float, pump_on: bool, duration: float):
        sql = 'INSERT INTO PH_DATA (UNIX_TIMESTAMP, TIMESTAMP, WATTS, PUMP_ON, DURATION) VALUES (?, ?, ?, ?, ?)'
        with self.connection:
            self.connection.execute(sql, (unix_ts, ts, watts, 1 if pump_on else 0, duration))
