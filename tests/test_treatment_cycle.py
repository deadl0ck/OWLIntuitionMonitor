"""Tests for monitor.treatment_cycle."""

from datetime import date, timedelta
from monitor.treatment_cycle import TreatmentCycle


def _cycle(interval: int = 5, start: int = 2, end: int = 4, min_dur: float = 3.0) -> TreatmentCycle:
    return TreatmentCycle(
        label='test',
        interval_days=interval,
        utc_start_hour=start,
        utc_end_hour=end,
        min_duration_minutes=min_dur,
    )


# --- covers_hour ---

def test_covers_hour_inside_window() -> None:
    assert _cycle(start=2, end=4).covers_hour(2) is True
    assert _cycle(start=2, end=4).covers_hour(3) is True


def test_covers_hour_at_end_exclusive() -> None:
    assert _cycle(start=2, end=4).covers_hour(4) is False


def test_covers_hour_outside_window() -> None:
    assert _cycle(start=2, end=4).covers_hour(1) is False
    assert _cycle(start=2, end=4).covers_hour(5) is False


# --- is_due ---

def test_is_due_returns_false_when_next_expected_none() -> None:
    c = _cycle(interval=3)
    assert c.next_expected_date is None
    assert c.is_due(date(2026, 1, 10)) is False


def test_is_due_returns_true_on_exact_expected_date() -> None:
    c = _cycle(interval=5)
    c.next_expected_date = date(2026, 1, 6)
    assert c.is_due(date(2026, 1, 6)) is True


def test_is_due_returns_false_day_before_expected() -> None:
    c = _cycle(interval=5)
    c.next_expected_date = date(2026, 1, 6)
    assert c.is_due(date(2026, 1, 5)) is False


def test_is_due_returns_false_day_after_expected() -> None:
    c = _cycle(interval=5)
    c.next_expected_date = date(2026, 1, 6)
    assert c.is_due(date(2026, 1, 7)) is False


def test_is_due_returns_false_far_before_expected() -> None:
    c = _cycle(interval=14)
    c.next_expected_date = date(2026, 1, 15)
    assert c.is_due(date(2026, 1, 1)) is False


# --- advance_schedule ---

def test_advance_schedule_increments_by_interval() -> None:
    c = _cycle(interval=5)
    c.next_expected_date = date(2026, 1, 6)
    c.advance_schedule()
    assert c.next_expected_date == date(2026, 1, 11)


def test_advance_schedule_is_cumulative() -> None:
    c = _cycle(interval=3)
    c.next_expected_date = date(2026, 1, 1)
    c.advance_schedule()
    c.advance_schedule()
    assert c.next_expected_date == date(2026, 1, 7)


def test_advance_schedule_does_nothing_when_none() -> None:
    c = _cycle(interval=5)
    c.next_expected_date = None
    c.advance_schedule()
    assert c.next_expected_date is None
