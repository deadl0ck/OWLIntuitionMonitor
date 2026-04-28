"""UDP multicast listener that receives, parses and processes OWL Intuition power readings."""

import logging
import socket
import struct
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import time
from monitor.email_sender import EmailSender
from monitor.database import Database

logger = logging.getLogger(__name__)


class DataReceiver:
    """Joins the OWL Intuition multicast group and processes incoming power readings."""

    def __init__(self,
                 group: str,
                 port: int,
                 email: EmailSender,
                 email_receiver: str,
                 alarm_threshold: int,
                 pump_threshold_watts: float,
                 db: Database) -> None:
        """Bind a UDP socket and join the multicast group.

        Args:
            group: Multicast group IP address (e.g. '224.192.32.19').
            port: UDP port the OWL device broadcasts on.
            email: EmailSender instance used to dispatch alerts.
            email_receiver: Address that alert emails are sent to.
            alarm_threshold: Minutes of continuous pump activity before alerting.
            pump_threshold_watts: Watts above which the pump is considered on.
            db: Database instance for persisting readings.
        """
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('', port))
        group_bytes = socket.inet_aton(group)
        multicast_req = struct.pack('4sI', group_bytes, socket.INADDR_ANY)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, multicast_req)

        self.email = email
        self.alarm_threshold = alarm_threshold
        self.pump_threshold_watts = pump_threshold_watts
        self.db = db
        self.email_receiver = email_receiver

        self._pump_on = False
        self._pump_state_change_ts: float = time.time()
        self._email_sent_for_current_run = False
        self._first_reading = True

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
        """Update pump state, persist the reading and send alerts when needed.

        Detects on/off transitions by comparing current watts against
        pump_threshold_watts. Sends an in-progress alert when the pump exceeds
        the alarm threshold and a completion alert when a long run finishes.

        Args:
            unix_ts: Reading time as a Unix timestamp.
            watts: Power reading in watts.
        """
        date_time = datetime.fromtimestamp(unix_ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        pump_already_on = self._pump_on
        self._pump_on = watts > self.pump_threshold_watts
        pump_off = not self._pump_on
        duration = (unix_ts - self._pump_state_change_ts) / 60

        self.db.insert_reading(unix_ts, date_time, watts, self._pump_on, duration)

        if pump_off:
            self._email_sent_for_current_run = False

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
            logger.info(f'Pump has just finished — ran for {duration:.1f} minutes')
            if duration > self.alarm_threshold:
                self.email.send(self.email_receiver,
                                f'PUMPHOUSE: {duration:.1f} minute(s) run finished',
                                f'Pump finished long run - it was running for {duration:.1f} minute(s)')
            self._pump_state_change_ts = unix_ts
            return

        if self._pump_on and duration > self.alarm_threshold and not self._email_sent_for_current_run:
            self.email.send(self.email_receiver,
                            f'PUMPHOUSE: Running over {self.alarm_threshold} minute(s)',
                            f'Pump running for over threshold duration of {self.alarm_threshold} minute(s)')
            self._email_sent_for_current_run = True
            logger.info(f'Pump over threshold — alert sent after {duration:.1f} minutes')

    def receive_data(self) -> None:
        """Block forever, receiving and processing UDP multicast readings.

        Sends a startup email on entry, then loops continuously. Each received
        packet is parsed and passed to _process_reading. Exceptions within the
        loop are logged and swallowed so the monitor never stops due to a
        transient error.
        """
        message = f'Pumphouse monitoring starting — alarm threshold is {self.alarm_threshold} minute(s)'
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
