"""UDP multicast listener that receives, parses and processes OWL Intuition power readings."""

import logging
import socket
import struct
from bs4 import BeautifulSoup
from datetime import date, datetime, timezone, timedelta
import time
from monitor.email_sender import EmailSender
from monitor.database import Database
from monitor.treatment_cycle import TreatmentCycle

logger = logging.getLogger(__name__)


class DataReceiver:
    """Joins the OWL Intuition multicast group and processes incoming power readings."""

    def __init__(self,
                 group: str,
                 port: int,
                 email: EmailSender,
                 email_receiver: str,
                 pump_threshold_watts: float,
                 db: Database,
                 cycles: list[TreatmentCycle],
                 summary_day: int,
                 summary_hour_utc: int,
                 unexpected_alert_threshold: float) -> None:
        """Bind a UDP socket and join the multicast group.

        Args:
            group: Multicast group IP address (e.g. '224.192.32.19').
            port: UDP port the OWL device broadcasts on.
            email: EmailSender instance used to dispatch alerts.
            email_receiver: Address that alert emails are sent to.
            pump_threshold_watts: Watts above which the pump is considered on.
            db: Database instance for persisting readings.
            cycles: Treatment cycle definitions (time window + interval + threshold).
            summary_day: Weekday on which to send weekly summary (0=Monday).
            summary_hour_utc: UTC hour after which to send the weekly summary.
            unexpected_alert_threshold: Minutes above which an out-of-window run triggers an alert.
        """
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('', port))
        group_bytes = socket.inet_aton(group)
        multicast_req = struct.pack('4sI', group_bytes, socket.INADDR_ANY)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, multicast_req)

        self.email = email
        self.pump_threshold_watts = pump_threshold_watts
        self.db = db
        self.email_receiver = email_receiver
        self.cycles = cycles
        self.summary_day = summary_day
        self.summary_hour_utc = summary_hour_utc
        self.unexpected_alert_threshold = unexpected_alert_threshold

        self._pump_on = False
        self._pump_state_change_ts: float = time.time()
        self._first_reading = True
        self._current_date: date | None = None
        # (date, cycle_label) → cumulative pump-on minutes in that window on that date
        self._window_minutes: dict[tuple[date, str], float] = {}
        self._last_summary_week: int | None = None

    def _init_cycle_last_runs(self) -> None:
        """Seed each cycle's last_run_date from the database on startup."""
        for cycle in self.cycles:
            last = self.db.get_last_run_date_in_window(
                cycle.utc_start_hour, cycle.utc_end_hour, cycle.min_duration_minutes
            )
            cycle.last_run_date = last
            if last:
                logger.info(f'{cycle.label}: last confirmed run {last}')
            else:
                logger.warning(f'{cycle.label}: no prior run found in DB — will not alert until first run is seen')

    def _parse_reading(self, xml: str) -> tuple[int, float] | None:
        """Parse an OWL Intuition XML broadcast into a timestamp and wattage.

        Args:
            xml: Raw XML string received from the multicast socket.

        Returns:
            A (unix_timestamp, watts) tuple, or None if the XML is missing
            required elements and should be discarded.
        """
        soup = BeautifulSoup(xml, "lxml")
        if soup.electricity is None or soup.electricity.timestamp is None:
            return None
        chan = soup.electricity.find("chan")
        if chan is None:
            logger.warning('Missing chan element in received packet')
            return None
        ts = int(soup.electricity.timestamp.text)
        watts = float(chan.curr.text)
        return ts, watts

    def _process_reading(self, unix_ts: int, watts: float) -> None:
        """Update pump state, persist the reading and check treatment schedules.

        Detects on/off transitions by comparing current watts against
        pump_threshold_watts. On pump-off transitions, accumulates run time into
        the matching treatment window. At each date rollover, checks for missed
        treatments and (on the configured weekday) sends a weekly summary.

        Args:
            unix_ts: Reading time as a Unix timestamp.
            watts: Power reading in watts.
        """
        reading_dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
        date_time = reading_dt.strftime('%Y-%m-%d %H:%M:%S')
        reading_date = reading_dt.date()
        reading_hour = reading_dt.hour

        pump_already_on = self._pump_on
        self._pump_on = watts > self.pump_threshold_watts
        pump_off = not self._pump_on
        duration = (unix_ts - self._pump_state_change_ts) / 60

        self.db.insert_reading(unix_ts, date_time, watts, self._pump_on, duration)

        # Day rollover — check missed treatments for the day that just ended
        if self._current_date is not None and reading_date > self._current_date:
            self._check_missed_treatments(self._current_date)
            self._maybe_send_weekly_summary(reading_date, reading_hour)
        self._current_date = reading_date

        if self._pump_on and not pump_already_on:
            self._pump_state_change_ts = unix_ts
            if self._first_reading:
                logger.warning(
                    'Pump appears to already be running at monitor start — '
                    'duration will be measured from now, not actual pump start'
                )
            else:
                logger.info('Pump has just started')
            self._first_reading = False
            return

        self._first_reading = False

        if pump_off and pump_already_on:
            pump_start_dt = datetime.fromtimestamp(self._pump_state_change_ts, tz=timezone.utc)
            pump_start_date = pump_start_dt.date()
            pump_start_hour = pump_start_dt.hour
            logger.info(f'Pump has just finished — ran for {duration:.1f} minutes')
            matched_cycle = next(
                (c for c in self.cycles if c.covers_hour(pump_start_hour)), None
            )
            if matched_cycle:
                key = (pump_start_date, matched_cycle.label)
                self._window_minutes[key] = self._window_minutes.get(key, 0.0) + duration
                if duration >= matched_cycle.min_duration_minutes:
                    matched_cycle.last_run_date = pump_start_date
                    logger.info(f'{matched_cycle.label} treatment run confirmed ({duration:.1f} min)')
            elif duration >= self.unexpected_alert_threshold:
                pump_start_str = pump_start_dt.strftime('%Y-%m-%d %H:%M UTC')
                self.email.send(
                    self.email_receiver,
                    f'PUMPHOUSE: Unexpected run on {pump_start_date}',
                    f'Pump ran for {duration:.1f} minutes starting at {pump_start_str}.\n'
                    f'This run was outside all expected treatment windows.',
                )
                logger.warning(
                    f'Unexpected run on {pump_start_date} at {pump_start_str} '
                    f'— {duration:.1f} min'
                )
            self._pump_state_change_ts = unix_ts
            return

    def _check_missed_treatments(self, prev_date: date) -> None:
        """Send alerts for any treatment cycles that were due but did not run on prev_date."""
        for cycle in self.cycles:
            if not cycle.is_due(prev_date):
                continue
            minutes = self._window_minutes.get((prev_date, cycle.label), 0.0)
            if minutes < cycle.min_duration_minutes:
                self.email.send(
                    self.email_receiver,
                    f'PUMPHOUSE: Missed {cycle.label} treatment on {prev_date}',
                    f'Expected {cycle.label} treatment on {prev_date} did not run.\n'
                    f'Pump activity in window: {minutes:.1f} min '
                    f'(minimum expected: {cycle.min_duration_minutes} min).',
                )
                logger.warning(
                    f'Missed {cycle.label} treatment on {prev_date} '
                    f'— only {minutes:.1f} min in window'
                )
            else:
                logger.info(
                    f'{cycle.label} treatment on {prev_date} confirmed '
                    f'({minutes:.1f} min in window)'
                )

    def _maybe_send_weekly_summary(self, today: date, hour: int) -> None:
        """Send the weekly summary email if today is the configured summary day and hour."""
        if today.weekday() != self.summary_day:
            return
        if hour < self.summary_hour_utc:
            return
        iso_week = today.isocalendar().week
        if self._last_summary_week == iso_week:
            return
        self._last_summary_week = iso_week
        self._send_weekly_summary(today)

    def _send_weekly_summary(self, today: date) -> None:
        """Build and send a weekly summary of all pump runs from the previous 7 days."""
        week_start = today - timedelta(days=7)
        start_ts = int(datetime(week_start.year, week_start.month, week_start.day,
                                tzinfo=timezone.utc).timestamp())
        end_ts = int(datetime(today.year, today.month, today.day,
                              tzinfo=timezone.utc).timestamp())

        rows = self.db.get_runs_between(start_ts, end_ts)

        lines = [
            f'Weekly pump activity: {week_start} to {today - timedelta(days=1)}',
            '',
            f'{"Date":<12} {"Time (UTC)":<12} {"Duration":>10}  {"Type"}',
            '-' * 52,
        ]

        for ts, dur in rows:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            run_date = dt.strftime('%Y-%m-%d')
            run_time = dt.strftime('%H:%M')
            run_hour = dt.hour
            label = next(
                (c.label for c in self.cycles if c.covers_hour(run_hour)),
                'unexpected'
            )
            lines.append(f'{run_date:<12} {run_time:<12} {dur:>8.1f} min  {label}')

        if not rows:
            lines.append('No pump activity recorded.')

        body = '\n'.join(lines)
        self.email.send(
            self.email_receiver,
            f'PUMPHOUSE: Weekly summary ({week_start} to {today - timedelta(days=1)})',
            body,
        )
        logger.info(f'Weekly summary sent for {week_start} to {today - timedelta(days=1)}')

    def receive_data(self) -> None:
        """Block forever, receiving and processing UDP multicast readings.

        Seeds cycle last-run dates from the DB, sends a startup email, then loops
        continuously. Each received packet is parsed and passed to _process_reading.
        Exceptions within the loop are logged and swallowed so the monitor never
        stops due to a transient error.
        """
        self._init_cycle_last_runs()
        message = (
            f'Pumphouse monitoring starting — '
            f'tracking {len(self.cycles)} treatment cycle(s): '
            + ', '.join(f'{c.label} (every {c.interval_days} nights)' for c in self.cycles)
        )
        logger.info(message)
        self.email.send(self.email_receiver, 'PUMPHOUSE: Monitor Starting', message)

        while True:
            try:
                enc_data, _ = self.sock.recvfrom(4096)
                reading = self._parse_reading(enc_data.decode('utf-8'))
                if reading is None:
                    continue
                self._process_reading(*reading)
            except Exception:
                logger.exception('Unexpected error processing reading — continuing')
