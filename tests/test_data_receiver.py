"""Tests for monitor.data_receiver — covers XML parsing and the pump state machine."""

import pytest
from datetime import date
from unittest.mock import patch, MagicMock, call
from monitor.data_receiver import DataReceiver
from monitor.treatment_cycle import TreatmentCycle

# Minimal XML samples that match the OWL Intuition broadcast format
HIGH_WATTS_XML = (
    '<electricity id="443719D3">'
    '<timestamp>1700000000</timestamp>'
    '<chan id="0"><curr units="w">1500.00</curr></chan>'
    '</electricity>'
)
LOW_WATTS_XML = (
    '<electricity id="443719D3">'
    '<timestamp>1700000000</timestamp>'
    '<chan id="0"><curr units="w">200.00</curr></chan>'
    '</electricity>'
)
NO_ELECTRICITY_XML = '<other>data</other>'
NO_TIMESTAMP_XML = (
    '<electricity id="443719D3">'
    '<chan id="0"><curr units="w">1500.00</curr></chan>'
    '</electricity>'
)
NO_CHAN_XML = '<electricity id="443719D3"><timestamp>1700000000</timestamp></electricity>'


def _make_cycle(label: str = 'test', interval: int = 5, start_h: int = 2,
                end_h: int = 4, min_dur: float = 3.0,
                last_run: date | None = None) -> TreatmentCycle:
    c = TreatmentCycle(
        label=label, interval_days=interval,
        utc_start_hour=start_h, utc_end_hour=end_h,
        min_duration_minutes=min_dur,
    )
    c.last_run_date = last_run
    return c


@pytest.fixture
def receiver() -> DataReceiver:
    """Return a DataReceiver with a mocked socket and dummy email/db dependencies."""
    with patch('socket.socket'), patch('socket.inet_aton', return_value=b'\xe0\xc0\x20\x13'):
        r = DataReceiver(
            group="224.192.32.19",
            port=22600,
            email=MagicMock(),
            email_receiver="recv@test.com",
            pump_threshold_watts=1000.0,
            db=MagicMock(),
            cycles=[],
            summary_day=0,
            summary_hour_utc=7,
            unexpected_alert_threshold=7.0,
        )
        return r


# --- _parse_reading ---

def test_parse_valid_xml_returns_ts_and_watts(receiver: DataReceiver) -> None:
    """Verify that a well-formed broadcast is parsed into (timestamp, watts)."""
    assert receiver._parse_reading(HIGH_WATTS_XML) == (1700000000, 1500.0)


def test_parse_low_watts_xml(receiver: DataReceiver) -> None:
    """Verify that low-wattage readings are parsed correctly."""
    assert receiver._parse_reading(LOW_WATTS_XML) == (1700000000, 200.0)


def test_parse_missing_electricity_element_returns_none(receiver: DataReceiver) -> None:
    """Verify that XML without an <electricity> element is discarded."""
    assert receiver._parse_reading(NO_ELECTRICITY_XML) is None


def test_parse_missing_timestamp_returns_none(receiver: DataReceiver) -> None:
    """Verify that XML without a <timestamp> element is discarded."""
    assert receiver._parse_reading(NO_TIMESTAMP_XML) is None


def test_parse_missing_chan_returns_none(receiver: DataReceiver) -> None:
    """Verify that XML without a <chan> element is discarded."""
    assert receiver._parse_reading(NO_CHAN_XML) is None


# --- _process_reading: pump start ---

def test_pump_start_updates_state_change_timestamp(receiver: DataReceiver) -> None:
    """Verify that the state-change timestamp is set to the current reading time on start."""
    receiver._pump_on = False
    receiver._process_reading(1700000000, 1500.0)
    assert receiver._pump_state_change_ts == 1700000000


def test_pump_start_does_not_send_email(receiver: DataReceiver) -> None:
    """Verify that no alert email is sent the moment the pump turns on."""
    receiver._pump_on = False
    receiver._process_reading(1700000000, 1500.0)
    receiver.email.send.assert_not_called()


def test_pump_start_is_written_to_database(receiver: DataReceiver) -> None:
    """Verify that the reading is persisted even when the pump has just started."""
    receiver._pump_on = False
    receiver._process_reading(1700000000, 1500.0)
    receiver.db.insert_reading.assert_called_once()


def test_pump_already_on_at_startup_logs_warning(receiver: DataReceiver, caplog) -> None:
    """Verify that a warning is logged when the pump appears to be running at monitor start."""
    receiver._pump_on = False
    receiver._first_reading = True
    with caplog.at_level('WARNING'):
        receiver._process_reading(1700000000, 1500.0)
    assert 'already be running at monitor start' in caplog.text


def test_pump_already_on_at_startup_does_not_send_email(receiver: DataReceiver) -> None:
    """Verify that detecting pump-on on the first reading does not send an alert."""
    receiver._pump_on = False
    receiver._first_reading = True
    receiver._process_reading(1700000000, 1500.0)
    receiver.email.send.assert_not_called()


# --- _process_reading: pump running ---

def test_pump_running_no_email(receiver: DataReceiver) -> None:
    """Verify that no email is sent while the pump continues to run."""
    receiver._pump_on = True
    receiver._first_reading = False
    receiver._pump_state_change_ts = 1700000000 - (30 * 60)  # 30 min run
    receiver._process_reading(1700000000, 1500.0)
    receiver.email.send.assert_not_called()


# --- _process_reading: pump stop ---

def test_pump_stop_in_treatment_window_does_not_send_email(receiver: DataReceiver) -> None:
    """Verify that no email is sent when a pump run ends within a treatment window."""
    from datetime import datetime, timezone
    cycle = _make_cycle(label='3-night', interval=3, start_h=4, end_h=5, min_dur=8.0)
    receiver.cycles = [cycle]
    pump_start = int(datetime(2026, 2, 2, 4, 10, 0, tzinfo=timezone.utc).timestamp())
    receiver._pump_on = True
    receiver._first_reading = False
    receiver._pump_state_change_ts = pump_start
    receiver._process_reading(pump_start + 20 * 60, 200.0)
    receiver.email.send.assert_not_called()


def test_pump_stop_updates_state_change_timestamp(receiver: DataReceiver) -> None:
    """Verify that the state-change timestamp is updated when the pump stops."""
    receiver._pump_on = True
    receiver._first_reading = False
    receiver._pump_state_change_ts = 1700000000 - 60
    receiver._process_reading(1700000000, 200.0)
    assert receiver._pump_state_change_ts == 1700000000


def test_pump_stop_accumulates_window_minutes(receiver: DataReceiver) -> None:
    """Verify that a pump run within a treatment window accumulates into _window_minutes."""
    cycle = _make_cycle(label='3-night', interval=3, start_h=4, end_h=5, min_dur=8.0)
    receiver.cycles = [cycle]
    # Pump started at 04:10 UTC on 2023-11-14 (1700000000 = 2023-11-14 22:13 UTC, use offset)
    # Use a timestamp that falls in the 04:xx UTC hour
    pump_start_ts = 1700000000  # arbitrary
    from datetime import datetime, timezone
    # Choose a start time in 04:xx UTC
    dt_04 = datetime(2024, 1, 15, 4, 10, 0, tzinfo=timezone.utc)
    pump_start = int(dt_04.timestamp())
    pump_end = pump_start + 12 * 60  # 12 min run
    receiver._pump_on = True
    receiver._first_reading = False
    receiver._pump_state_change_ts = pump_start
    receiver._process_reading(pump_end, 200.0)  # pump off
    key = (dt_04.date(), '3-night')
    assert receiver._window_minutes.get(key, 0.0) == pytest.approx(12.0, abs=0.1)


def test_pump_stop_confirms_cycle_when_above_min_duration(receiver: DataReceiver) -> None:
    """Verify that cycle.last_run_date is updated when a run meets the minimum duration."""
    from datetime import datetime, timezone
    cycle = _make_cycle(label='3-night', interval=3, start_h=4, end_h=5, min_dur=8.0)
    receiver.cycles = [cycle]
    dt_04 = datetime(2024, 1, 15, 4, 10, 0, tzinfo=timezone.utc)
    pump_start = int(dt_04.timestamp())
    pump_end = pump_start + 12 * 60
    receiver._pump_on = True
    receiver._first_reading = False
    receiver._pump_state_change_ts = pump_start
    receiver._process_reading(pump_end, 200.0)
    assert cycle.last_run_date == dt_04.date()


def test_pump_stop_does_not_confirm_cycle_below_min_duration(receiver: DataReceiver) -> None:
    """Verify that cycle.last_run_date is NOT updated for a run below minimum duration."""
    from datetime import datetime, timezone
    cycle = _make_cycle(label='3-night', interval=3, start_h=4, end_h=5, min_dur=8.0)
    cycle.last_run_date = None
    receiver.cycles = [cycle]
    dt_04 = datetime(2024, 1, 15, 4, 10, 0, tzinfo=timezone.utc)
    pump_start = int(dt_04.timestamp())
    pump_end = pump_start + 5 * 60  # only 5 min, below 8 min threshold
    receiver._pump_on = True
    receiver._first_reading = False
    receiver._pump_state_change_ts = pump_start
    receiver._process_reading(pump_end, 200.0)
    assert cycle.last_run_date is None


# --- unexpected run alerts ---

def test_unexpected_run_over_threshold_sends_alert(receiver: DataReceiver) -> None:
    """Verify that a run outside all treatment windows triggers an alert when over threshold."""
    from datetime import datetime, timezone
    # 10:00 UTC is outside all treatment windows (01-02, 02-04, 04-05)
    pump_start = int(datetime(2026, 2, 2, 10, 0, 0, tzinfo=timezone.utc).timestamp())
    pump_end = pump_start + 10 * 60  # 10 min, over 7 min threshold
    receiver._pump_on = True
    receiver._first_reading = False
    receiver._pump_state_change_ts = pump_start
    receiver._process_reading(pump_end, 200.0)
    receiver.email.send.assert_called_once()
    subject = receiver.email.send.call_args[0][1]
    assert 'Unexpected' in subject


def test_unexpected_run_under_threshold_no_alert(receiver: DataReceiver) -> None:
    """Verify that a short out-of-window run does not trigger an alert."""
    from datetime import datetime, timezone
    pump_start = int(datetime(2026, 2, 2, 10, 0, 0, tzinfo=timezone.utc).timestamp())
    pump_end = pump_start + 5 * 60  # 5 min, under 7 min threshold
    receiver._pump_on = True
    receiver._first_reading = False
    receiver._pump_state_change_ts = pump_start
    receiver._process_reading(pump_end, 200.0)
    receiver.email.send.assert_not_called()


def test_run_in_treatment_window_no_unexpected_alert(receiver: DataReceiver) -> None:
    """Verify that a run inside a treatment window does not send an unexpected alert."""
    from datetime import datetime, timezone
    cycle = _make_cycle(label='3-night', interval=3, start_h=4, end_h=5, min_dur=8.0)
    receiver.cycles = [cycle]
    pump_start = int(datetime(2026, 2, 2, 4, 10, 0, tzinfo=timezone.utc).timestamp())
    pump_end = pump_start + 12 * 60  # 12 min, in 04:xx window
    receiver._pump_on = True
    receiver._first_reading = False
    receiver._pump_state_change_ts = pump_start
    receiver._process_reading(pump_end, 200.0)
    receiver.email.send.assert_not_called()


# --- _check_missed_treatments ---

def test_missed_treatment_sends_alert(receiver: DataReceiver) -> None:
    """Verify that an alert is sent when a due cycle had no sufficient activity."""
    cycle = _make_cycle(label='5-night', interval=5, start_h=2, end_h=4, min_dur=3.0,
                        last_run=date(2026, 1, 1))
    receiver.cycles = [cycle]
    # No activity recorded for Jan 6 (5 days later)
    receiver._check_missed_treatments(date(2026, 1, 6))
    receiver.email.send.assert_called_once()
    subject = receiver.email.send.call_args[0][1]
    assert 'Missed' in subject and '5-night' in subject


def test_treatment_confirmed_no_alert(receiver: DataReceiver) -> None:
    """Verify that no alert is sent when a due cycle had sufficient activity."""
    cycle = _make_cycle(label='5-night', interval=5, start_h=2, end_h=4, min_dur=3.0,
                        last_run=date(2026, 1, 1))
    receiver.cycles = [cycle]
    receiver._window_minutes[(date(2026, 1, 6), '5-night')] = 4.5  # sufficient
    receiver._check_missed_treatments(date(2026, 1, 6))
    receiver.email.send.assert_not_called()


def test_not_due_cycle_no_alert(receiver: DataReceiver) -> None:
    """Verify that no alert is sent when a cycle is not yet due."""
    cycle = _make_cycle(label='5-night', interval=5, start_h=2, end_h=4, min_dur=3.0,
                        last_run=date(2026, 1, 1))
    receiver.cycles = [cycle]
    # Only 3 days since last run — not due for 5-night
    receiver._check_missed_treatments(date(2026, 1, 4))
    receiver.email.send.assert_not_called()


def test_no_last_run_date_no_alert(receiver: DataReceiver) -> None:
    """Verify that no alert is sent when last_run_date is None (first cycle not yet seen)."""
    cycle = _make_cycle(label='5-night', interval=5, start_h=2, end_h=4, min_dur=3.0,
                        last_run=None)
    receiver.cycles = [cycle]
    receiver._check_missed_treatments(date(2026, 1, 6))
    receiver.email.send.assert_not_called()


# --- date rollover ---

def test_date_rollover_triggers_missed_treatment_check(receiver: DataReceiver) -> None:
    """Verify that processing a reading on a new date triggers the missed treatment check."""
    from unittest.mock import patch as _patch
    cycle = _make_cycle(label='5-night', interval=5, start_h=2, end_h=4, min_dur=3.0,
                        last_run=date(2026, 1, 1))
    receiver.cycles = [cycle]
    # First reading on Jan 6 sets _current_date
    receiver._pump_on = False
    receiver._first_reading = False
    ts_jan6 = int(__import__('datetime').datetime(2026, 1, 6, 10, 0, tzinfo=__import__('datetime').timezone.utc).timestamp())
    receiver._process_reading(ts_jan6, 200.0)
    assert receiver._current_date == date(2026, 1, 6)
    # Reading on Jan 7 triggers check for Jan 6
    ts_jan7 = int(__import__('datetime').datetime(2026, 1, 7, 10, 0, tzinfo=__import__('datetime').timezone.utc).timestamp())
    receiver._process_reading(ts_jan7, 200.0)
    # Missed alert should have been sent for Jan 6
    receiver.email.send.assert_called_once()


# --- receive_data ---

def test_receive_data_sends_startup_email(receiver: DataReceiver) -> None:
    """Verify that a startup notification email is sent before the receive loop begins."""
    receiver.sock.recvfrom.side_effect = KeyboardInterrupt()
    receiver.db.get_last_run_date_in_window.return_value = None
    with pytest.raises(KeyboardInterrupt):
        receiver.receive_data()
    receiver.email.send.assert_called_once()
    assert receiver.email.send.call_args[0][1] == 'PUMPHOUSE: Monitor Starting'


def test_receive_data_continues_after_exception(receiver: DataReceiver) -> None:
    """Verify that a transient error inside the loop is swallowed and the loop keeps running."""
    receiver.sock.recvfrom.side_effect = [
        Exception("transient socket error"),
        KeyboardInterrupt(),
    ]
    receiver.db.get_last_run_date_in_window.return_value = None
    with pytest.raises(KeyboardInterrupt):
        receiver.receive_data()
