"""Entry point for the OWL Intuition pumphouse monitor.

Loads configuration from .env (secrets) and config.ini (settings), then starts
the UDP multicast listener which records readings and sends Gmail alerts.
"""

import configparser
import logging
import os
from dotenv import load_dotenv
from monitor.email_sender import EmailSender
from monitor.database import Database
from monitor.data_receiver import DataReceiver
from monitor.treatment_cycle import TreatmentCycle

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

load_dotenv()

config = configparser.ConfigParser()
config.read('config.ini')

GMAIL_APP_PASSWORD = os.environ['GMAIL_APP_PASSWORD']
MULTICAST_GROUP = os.environ['MULTICAST_GROUP']
MULTICAST_PORT = config.getint('network', 'multicast_port')
DB_FILENAME = config.get('database', 'filename')
EMAIL_SENDER = config.get('email', 'sender')
EMAIL_RECEIVER = config.get('email', 'receiver')
PUMP_THRESHOLD_WATTS = config.getfloat('monitor', 'pump_threshold_watts')
UNEXPECTED_ALERT_THRESHOLD = config.getfloat('monitor', 'unexpected_alert_threshold_minutes')

_WEEKDAYS = {
    'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3,
    'Friday': 4, 'Saturday': 5, 'Sunday': 6,
}

cycles: list[TreatmentCycle] = []
for part in config.get('treatment', 'cycles').split('|'):
    interval_s, start_h_s, end_h_s, min_dur_s, label = part.strip().split(',')
    cycles.append(TreatmentCycle(
        label=label.strip(),
        interval_days=int(interval_s),
        utc_start_hour=int(start_h_s),
        utc_end_hour=int(end_h_s),
        min_duration_minutes=float(min_dur_s),
    ))

summary_day = _WEEKDAYS[config.get('treatment', 'summary_day')]
summary_hour_utc = config.getint('treatment', 'summary_hour_utc')

db = Database(DB_FILENAME)
email = EmailSender(EMAIL_SENDER, GMAIL_APP_PASSWORD)
receiver = DataReceiver(
    MULTICAST_GROUP,
    MULTICAST_PORT,
    email,
    EMAIL_RECEIVER,
    PUMP_THRESHOLD_WATTS,
    db,
    cycles=cycles,
    summary_day=summary_day,
    summary_hour_utc=summary_hour_utc,
    unexpected_alert_threshold=UNEXPECTED_ALERT_THRESHOLD,
)

receiver.receive_data()
