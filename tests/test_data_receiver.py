"""Tests for monitor.data_receiver — covers XML parsing and the pump state machine."""

import pytest
from unittest.mock import patch, MagicMock
from monitor.data_receiver import DataReceiver

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


@pytest.fixture
def receiver() -> DataReceiver:
    """Return a DataReceiver with a mocked socket and dummy email/db dependencies."""
    with patch('socket.socket'), patch('socket.inet_aton', return_value=b'\xe0\xc0\x20\x13'):
        r = DataReceiver(
            group="224.192.32.19",
            port=22600,
            email=MagicMock(),
            email_receiver="recv@test.com",
            alarm_threshold=5,
            db=MagicMock(),
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


# --- _process_reading: pump running ---

def test_pump_under_threshold_no_email(receiver: DataReceiver) -> None:
    """Verify that no alert is sent while the pump is running under the threshold."""
    receiver._pump_on = True
    receiver._pump_state_change_ts = 1700000000 - (3 * 60)  # 3 min, threshold is 5
    receiver._process_reading(1700000000, 1500.0)
    receiver.email.send.assert_not_called()


def test_pump_over_threshold_sends_alert_email(receiver: DataReceiver) -> None:
    """Verify that an alert email is sent when the pump exceeds the threshold."""
    receiver._pump_on = True
    receiver._pump_state_change_ts = 1700000000 - (6 * 60)  # 6 min, threshold is 5
    receiver._process_reading(1700000000, 1500.0)
    receiver.email.send.assert_called_once()
    assert 'Running over 5' in receiver.email.send.call_args[0][1]


def test_threshold_alert_sent_only_once_per_run(receiver: DataReceiver) -> None:
    """Verify that the threshold alert is not repeated on subsequent readings in the same run."""
    receiver._pump_on = True
    receiver._pump_state_change_ts = 1700000000 - (6 * 60)
    receiver._process_reading(1700000000, 1500.0)   # triggers alert
    receiver._process_reading(1700000030, 1500.0)   # same run, 30 s later
    assert receiver.email.send.call_count == 1


# --- _process_reading: pump stop ---

def test_pump_stop_after_long_run_sends_completion_email(receiver: DataReceiver) -> None:
    """Verify that a completion email is sent when a run exceeding the threshold finishes."""
    receiver._pump_on = True
    receiver._pump_state_change_ts = 1700000000 - (6 * 60)  # 6 min run
    receiver._process_reading(1700000000, 200.0)    # watts drop → pump off
    receiver.email.send.assert_called_once()
    assert 'run finished' in receiver.email.send.call_args[0][1]


def test_pump_stop_after_short_run_no_email(receiver: DataReceiver) -> None:
    """Verify that no email is sent when a short run finishes under the threshold."""
    receiver._pump_on = True
    receiver._pump_state_change_ts = 1700000000 - (2 * 60)  # 2 min run
    receiver._process_reading(1700000000, 200.0)
    receiver.email.send.assert_not_called()


def test_pump_stop_resets_email_flag(receiver: DataReceiver) -> None:
    """Verify that the email-sent flag is cleared when the pump stops."""
    receiver._pump_on = True
    receiver._email_sent_for_current_run = True
    receiver._pump_state_change_ts = 1700000000 - 60
    receiver._process_reading(1700000000, 200.0)    # pump off
    assert receiver._email_sent_for_current_run is False


def test_pump_stop_updates_state_change_timestamp(receiver: DataReceiver) -> None:
    """Verify that the state-change timestamp is updated when the pump stops."""
    receiver._pump_on = True
    receiver._pump_state_change_ts = 1700000000 - 60
    receiver._process_reading(1700000000, 200.0)
    assert receiver._pump_state_change_ts == 1700000000
