import socket
import struct
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import time
from email_sender import EmailSender
from database import Database
import sys

NUM_PROGRESS_DOTS_PER_LINE = 80


class DataReceiver:
    def __init__(self,
                 group: str,
                 port: int,
                 email: EmailSender,
                 email_receiver: str,
                 alarm_threshold: int,
                 db: Database):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('', port))
        group_bytes = socket.inet_aton(group)
        multicast_req = struct.pack('4sI', group_bytes, socket.INADDR_ANY)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, multicast_req)

        self.email = email
        self.alarm_threshold = alarm_threshold
        self.db = db
        self.email_receiver = email_receiver

        self._pump_on = False
        self._pump_state_change_ts: float = time.time()
        self._email_sent_for_current_run = False

    def _parse_reading(self, xml: str) -> tuple[int, float] | None:
        soup = BeautifulSoup(xml, "lxml")
        if soup.electricity is None or soup.electricity.timestamp is None:
            return None
        if soup.electricity.find("chan") is None:
            print(f'Missing chan element: {xml}')
            return None
        ts = int(soup.electricity.timestamp.text)
        watts = float(soup.electricity.find("chan").curr.text)
        return ts, watts

    def _process_reading(self, unix_ts: int, watts: float) -> None:
        date_time = datetime.fromtimestamp(unix_ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        pump_already_on = self._pump_on
        self._pump_on = watts > 1000.0
        pump_off = not self._pump_on
        duration = (unix_ts - self._pump_state_change_ts) / 60

        self.db.insert_reading(unix_ts, date_time, watts, self._pump_on, duration)

        if pump_off:
            self._email_sent_for_current_run = False

        if self._pump_on and not pump_already_on:
            self._pump_state_change_ts = unix_ts
            print("\nPump has just started")
            return

        if pump_off and pump_already_on:
            print(f'\nPump has just finished - it was running for {duration:.1f} minutes')
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

    def receive_data(self):
        message = f'Pumphouse monitoring starting - alarm threshold is {self.alarm_threshold} minute(s)'
        print(message)
        self.email.send(self.email_receiver, "PUMPHOUSE: Monitor Starting", message)

        dot_count = 0
        while True:
            enc_data, _ = self.sock.recvfrom(1024)
            reading = self._parse_reading(enc_data.decode("utf-8"))
            if reading is None:
                continue

            self._process_reading(*reading)

            if dot_count == NUM_PROGRESS_DOTS_PER_LINE:
                print("")
                dot_count = 0
            dot_count += 1
            sys.stdout.write(".")
            sys.stdout.flush()
