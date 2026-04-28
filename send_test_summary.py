#!/usr/bin/env python3
"""Send a test weekly summary email using real data from the database.

Usage:
    python3 send_test_summary.py           # last 7 days
    python3 send_test_summary.py --days 14 # last 14 days
"""

import argparse
import configparser
import os
import smtplib
import sys
from datetime import date, datetime, timezone, timedelta
from dotenv import load_dotenv
from monitor.email_sender import EmailSender
from monitor.database import Database
from monitor.treatment_cycle import TreatmentCycle
from monitor.data_receiver import _build_summary_text, _build_summary_html

load_dotenv()

config = configparser.ConfigParser()
config.read('config.ini')

parser = argparse.ArgumentParser(description='Send a test weekly summary email.')
parser.add_argument('--days', type=int, default=7, help='Number of past days to include (default: 7)')
args = parser.parse_args()

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

db = Database(config.get('database', 'filename'))
sender = EmailSender(config.get('email', 'sender'), os.environ['GMAIL_APP_PASSWORD'])
receiver_address = config.get('email', 'receiver')

today = date.today()
week_start = today - timedelta(days=args.days)
week_end = today - timedelta(days=1)
start_ts = int(datetime(week_start.year, week_start.month, week_start.day, tzinfo=timezone.utc).timestamp())
end_ts = int(datetime(today.year, today.month, today.day, tzinfo=timezone.utc).timestamp())

rows = db.get_runs_between(start_ts, end_ts)
tagged = []
for ts, dur in rows:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    label = next((c.label for c in cycles if c.covers_hour(dt.hour)), 'unexpected')
    tagged.append((dt, dur, label))

subject = f'PUMPHOUSE: Test summary ({week_start} to {week_end})'
text = _build_summary_text(week_start, week_end, tagged)
html = _build_summary_html(week_start, week_end, tagged)

print(f'Sending to {receiver_address} ...', flush=True)
print(flush=True)
print(f'Subject: {subject}', flush=True)
print(flush=True)
print(text, flush=True)
print(flush=True)

try:
    sender.send(receiver_address, subject, text, html=html)
    print('Sent.')
except smtplib.SMTPAuthenticationError:
    print('ERROR: Gmail authentication failed.', file=sys.stderr)
    print('  — Check GMAIL_APP_PASSWORD in .env is correct', file=sys.stderr)
    print('  — Check [email] sender in config.ini matches the Gmail account', file=sys.stderr)
    print('  — App Password must be generated at myaccount.google.com/apppasswords', file=sys.stderr)
    sys.exit(1)
except smtplib.SMTPException as e:
    print(f'ERROR: Failed to send email: {e}', file=sys.stderr)
    sys.exit(1)
