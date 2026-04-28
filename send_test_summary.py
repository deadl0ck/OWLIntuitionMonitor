#!/usr/bin/env python3
"""Send a test weekly summary email using real data from the database.

Usage:
    python3 send_test_summary.py           # last 7 days
    python3 send_test_summary.py --days 14 # last 14 days
"""

import argparse
import configparser
import os
import sys
from datetime import date, datetime, timezone, timedelta
from dotenv import load_dotenv
from monitor.email_sender import EmailSender
from monitor.database import Database
from monitor.treatment_cycle import TreatmentCycle

load_dotenv()

config = configparser.ConfigParser()
config.read('config.ini')

parser = argparse.ArgumentParser(description='Send a test weekly summary email.')
parser.add_argument('--days', type=int, default=7, help='Number of past days to include (default: 7)')
args = parser.parse_args()

# Build treatment cycles from config
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
email = EmailSender(config.get('email', 'sender'), os.environ['GMAIL_APP_PASSWORD'])
receiver_address = config.get('email', 'receiver')

today = date.today()
week_start = today - timedelta(days=args.days)
start_ts = int(datetime(week_start.year, week_start.month, week_start.day, tzinfo=timezone.utc).timestamp())
end_ts = int(datetime(today.year, today.month, today.day, tzinfo=timezone.utc).timestamp())

rows = db.get_runs_between(start_ts, end_ts)

lines = [
    f'Weekly pump activity: {week_start} to {today - timedelta(days=1)}',
    f'(Test email — {args.days}-day window ending today)',
    '',
    f'{"Date":<12} {"Time (UTC)":<12} {"Duration":>10}  {"Type"}',
    '-' * 52,
]

for ts, dur in rows:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    run_hour = dt.hour
    label = next((c.label for c in cycles if c.covers_hour(run_hour)), 'unexpected')
    lines.append(f'{dt.strftime("%Y-%m-%d"):<12} {dt.strftime("%H:%M"):<12} {dur:>8.1f} min  {label}')

if not rows:
    lines.append('No pump activity recorded in this period.')

body = '\n'.join(lines)
subject = f'PUMPHOUSE: Test summary ({week_start} to {today - timedelta(days=1)})'

print(f'Sending to {receiver_address} ...')
print()
print(f'Subject: {subject}')
print()
print(body)
print()

email.send(receiver_address, subject, body)
print('Sent.')
