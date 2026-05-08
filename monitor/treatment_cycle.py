"""Treatment cycle definition for pumphouse water treatment programs."""

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class TreatmentCycle:
    """Defines one recurring treatment program identified by its UTC time window.

    Args:
        label: Human-readable name (e.g. '3-night').
        interval_days: Expected days between runs (3, 5, or 14).
        utc_start_hour: UTC hour at which this program starts (inclusive).
        utc_end_hour: UTC hour at which this program ends (exclusive).
        min_duration_minutes: Minimum pump-on time to count as a valid treatment run.
        last_run_date: Most recent date on which a valid run was confirmed (seeded from DB
            at startup; updated as runs are observed).
        next_expected_date: The specific calendar date on which the next run is expected.
            Computed from last_run_date + interval_days on startup, then advanced by
            interval_days after each check (hit or miss). None until first run is seeded.
    """
    label: str
    interval_days: int
    utc_start_hour: int
    utc_end_hour: int
    min_duration_minutes: float
    last_run_date: date | None = field(default=None)
    next_expected_date: date | None = field(default=None)

    def covers_hour(self, hour: int) -> bool:
        """Return True if the given UTC hour falls within this cycle's window."""
        return self.utc_start_hour <= hour < self.utc_end_hour

    def is_due(self, on_date: date) -> bool:
        """Return True only if on_date is exactly the next scheduled run date.

        This ensures alerts fire only on the specific night a treatment is due,
        not on every subsequent night after a missed run accumulates overdue days.
        Returns False when next_expected_date is None (not yet seeded).
        """
        if self.next_expected_date is None:
            return False
        return on_date == self.next_expected_date

    def advance_schedule(self) -> None:
        """Advance next_expected_date by one interval after a check (hit or miss)."""
        if self.next_expected_date is not None:
            self.next_expected_date += timedelta(days=self.interval_days)
