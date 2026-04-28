import pytest
from monitor.database import Database


@pytest.fixture
def db():
    return Database(":memory:")


def test_table_is_created(db):
    cursor = db.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='PH_DATA'"
    )
    assert cursor.fetchone() is not None


def test_insert_reading_stores_all_values(db):
    db.insert_reading(1700000000, "2023-11-14 22:13:20", 1500.0, True, 2.5)
    row = db.connection.execute(
        "SELECT UNIX_TIMESTAMP, TIMESTAMP, WATTS, PUMP_ON, DURATION FROM PH_DATA"
    ).fetchone()
    assert row == (1700000000, "2023-11-14 22:13:20", 1500.0, 1, 2.5)


def test_pump_on_true_stored_as_one(db):
    db.insert_reading(1700000000, "2023-11-14 22:13:20", 1500.0, True, 1.0)
    assert db.connection.execute("SELECT PUMP_ON FROM PH_DATA").fetchone()[0] == 1


def test_pump_on_false_stored_as_zero(db):
    db.insert_reading(1700000000, "2023-11-14 22:13:20", 500.0, False, 1.0)
    assert db.connection.execute("SELECT PUMP_ON FROM PH_DATA").fetchone()[0] == 0


def test_multiple_readings_stored(db):
    db.insert_reading(1700000000, "2023-11-14 22:13:20", 1500.0, True, 1.0)
    db.insert_reading(1700000060, "2023-11-14 22:14:20", 1500.0, True, 2.0)
    count = db.connection.execute("SELECT COUNT(*) FROM PH_DATA").fetchone()[0]
    assert count == 2


def test_ids_autoincrement(db):
    db.insert_reading(1700000000, "2023-11-14 22:13:20", 1500.0, True, 1.0)
    db.insert_reading(1700000060, "2023-11-14 22:14:20", 1500.0, True, 2.0)
    ids = [row[0] for row in db.connection.execute("SELECT ID FROM PH_DATA").fetchall()]
    assert ids == [1, 2]
