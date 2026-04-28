"""Entry point for the OWL Intuition pumphouse monitor.

Loads configuration from .env (secrets) and config.ini (settings), then starts
the UDP multicast listener which records readings and sends Gmail alerts.
"""

import configparser
import os
from dotenv import load_dotenv
from monitor.email_sender import EmailSender
from monitor.database import Database
from monitor.data_receiver import DataReceiver

load_dotenv()

config = configparser.ConfigParser()
config.read('config.ini')

GMAIL_APP_PASSWORD = os.environ['GMAIL_APP_PASSWORD']
MULTICAST_GROUP = os.environ['MULTICAST_GROUP']
MULTICAST_PORT = config.getint('network', 'multicast_port')
DB_FILENAME = config.get('database', 'filename')
EMAIL_SENDER = config.get('email', 'sender')
EMAIL_RECEIVER = config.get('email', 'receiver')
ALARM_THRESHOLD = config.getint('monitor', 'alarm_threshold_minutes')

db = Database(DB_FILENAME)
email = EmailSender(EMAIL_SENDER, GMAIL_APP_PASSWORD)
receiver = DataReceiver(MULTICAST_GROUP,
                        MULTICAST_PORT,
                        email,
                        EMAIL_RECEIVER,
                        ALARM_THRESHOLD,
                        db)

receiver.receive_data()
