"""Treatment cycle definition for pumphouse water treatment programs."""

from dataclasses import dataclass, field
from datetime import date


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
    """
    label: str
    interval_days: int
    utc_start_hour: int
    utc_end_hour: int
    min_duration_minutes: float
    last_run_date: date | None = field(default=None)

    def covers_hour(self, hour: int) -> bool:
        """Return True if the given UTC hour falls within this cycle's window."""
        return self.utc_start_hour <= hour < self.utc_end_hour

    def is_due(self, on_date: date) -> bool:
        """Return True if this cycle should have run by on_date.

        Returns False when last_run_date is None (not yet seen) to avoid false
        alerts before the first confirmed run is observed.
        """
        if self.last_run_date is None:
            return False
        return (on_date - self.last_run_date).days >= self.interval_days
