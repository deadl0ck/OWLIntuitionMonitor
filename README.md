# OWL Intuition Power Monitor

Listens for UDP multicast data from an OWL Intuition power monitor and tracks electricity usage to a local SQLite database. When a monitored circuit (e.g. a pumphouse pump) runs longer than a configurable threshold, an alert email is sent via Gmail.

---

## Table of contents

- [Quickstart](#quickstart)
- [How it works](#how-it-works)
- [Directory structure](#directory-structure)
- [Setup](#setup)
- [Running](#running)
- [Logging](#logging)
- [Testing](#testing)
- [Database](#database)

---

## Quickstart

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd OWLIntuitionMonitor

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure secrets
cp .env.example .env
# Edit .env and fill in GMAIL_APP_PASSWORD and MULTICAST_GROUP

# 5. Configure application settings
# Edit config.ini — set your email addresses, thresholds, etc.

# 6. Run
python3 main.py
```

---

## How it works

The OWL Intuition device broadcasts power readings as XML over UDP multicast. This tool:
- Joins the multicast group and receives readings continuously
- Detects when power on the monitored channel crosses `pump_threshold_watts` (pump on/off)
- Records every reading to a SQLite database
- Tracks three recurring water treatment cycles (3-night, 5-night, 14-night), each identified
  by its UTC run window and minimum duration
- Emails an alert when an expected treatment night passes without sufficient pump activity
- Sends a weekly summary email (default: Monday morning) listing all runs tagged as expected
  or unexpected
- Sends a startup confirmation email when the monitor begins
- Logs a warning if the pump appears to already be running when monitoring starts

---

## Directory structure

```
OWLIntuitionMonitor/
├── main.py               # Entry point — loads config and starts the receiver
├── config.ini            # Application settings (port, email, thresholds)
├── .env.example          # Template for secrets — copy to .env and fill in
├── requirements.txt      # Python dependencies
│
├── monitor/              # Core application package
│   ├── database.py       # SQLite interface (creates table, inserts readings)
│   ├── data_receiver.py  # UDP multicast listener and pump state machine
│   ├── treatment_cycle.py  # Treatment cycle definition (time window + interval)
│   └── email_sender.py   # Gmail alert dispatcher
│
├── scripts/              # Shell scripts for managing the monitor process
│   ├── monitor_pumphouse.sh   # Start the monitor in the background
│   ├── restart_monitor.sh     # Kill any running instance and restart
│   ├── show_monitor_process.sh  # Check whether the monitor is running
│   ├── show_last_20_rows.sh   # Print the last 20 database rows
│   └── show_pump_on.sh        # Print rows where the pump was active
│
├── sql/                  # SQL queries used by the shell scripts above
│   ├── last_20_rows.sql
│   ├── pump_on.sql
│   ├── show_today.sql
│   └── today.sql
│
└── tests/                # pytest unit tests (no network or hardware required)
    ├── test_database.py
    ├── test_data_receiver.py
    ├── test_email_sender.py
    └── test_treatment_cycle.py
```

---

## Setup

### 1. Python version

Requires Python 3.10 or later (uses `X | Y` union type syntax). Developed against Python 3.13.

### 2. Virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows
```

Activate the virtual environment before running any `pip` or `python3` commands. To deactivate later, type `deactivate`.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure secrets — `.env`

Copy `.env.example` to `.env` and fill in your values. This file is gitignored and should never be committed.

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `GMAIL_APP_PASSWORD` | Gmail App Password — generate at myaccount.google.com/apppasswords (requires 2FA) |
| `MULTICAST_GROUP` | OWL Intuition multicast group address (e.g. `224.192.32.19`) |

### 5. Configure application settings — `config.ini`

Edit `config.ini` directly. These values are not secret and can be committed to version control.

| Setting | Description |
|---|---|
| `[network] multicast_port` | UDP port the OWL device broadcasts on (default: `22600`) |
| `[database] filename` | SQLite database file path |
| `[email] sender` | Gmail address used to send alerts |
| `[email] receiver` | Email address to receive alerts |
| `[monitor] pump_threshold_watts` | Watts above which the pump is considered on (default: `1000`) |
| `[treatment] cycles` | Pipe-separated list of treatment cycles — see format below |
| `[treatment] summary_day` | Day of week for the weekly summary email (default: `Monday`) |
| `[treatment] summary_hour_utc` | UTC hour after which the weekly summary is sent (default: `7`) |

**Treatment cycle format** — each entry in `cycles` is comma-separated:
`interval_days,utc_start_hour,utc_end_hour,min_duration_minutes,label`

Example (the default):
```
cycles = 14,1,2,15,14-night | 5,2,4,3,5-night | 3,4,5,8,3-night
```

| Field | Description |
|---|---|
| `interval_days` | Expected days between runs (e.g. `3`, `5`, `14`) |
| `utc_start_hour` | UTC hour the program starts (inclusive) |
| `utc_end_hour` | UTC hour the program ends (exclusive) |
| `min_duration_minutes` | Minimum pump-on time to count as a valid treatment run |
| `label` | Human-readable name used in alert subjects and the weekly summary |

An alert is sent if a cycle's UTC window shows less than `min_duration_minutes` of pump
activity on a date when the cycle was due. A cycle is considered due once
`(today - last_run_date) >= interval_days`. No alert is sent until the first run of each
cycle has been observed (seeded from the database on startup).

---

## Running

```bash
# Foreground — log output goes to the terminal
python3 main.py

# Background — log output goes to pumphouse_monitor.log
./scripts/monitor_pumphouse.sh

# Restart a running instance
./scripts/restart_monitor.sh

# Check if the monitor is running
./scripts/show_monitor_process.sh
```

Both shell scripts will exit with an error if `.env` is not found rather than starting with missing credentials.

---

## Logging

The monitor uses Python's standard `logging` module. All output is timestamped:

```
2026-03-06 04:14:01 INFO     Pumphouse monitoring starting — tracking 3 treatment cycle(s): 14-night (every 14 nights), 5-night (every 5 nights), 3-night (every 3 nights)
2026-03-06 04:14:01 INFO     14-night: last confirmed run 2026-03-05
2026-03-06 04:14:01 INFO     5-night: last confirmed run 2026-03-06
2026-03-06 04:14:01 INFO     3-night: last confirmed run 2026-03-06
2026-03-06 04:15:23 INFO     Pump has just started
2026-03-06 04:27:48 INFO     Pump has just finished — ran for 12.4 minutes
2026-03-06 04:27:48 INFO     3-night treatment run confirmed (12.4 min)
2026-03-07 07:00:05 INFO     3-night treatment on 2026-03-06 confirmed (12.4 min in window)
2026-03-12 07:00:05 WARNING  Missed 5-night treatment on 2026-03-11 — only 0.0 min in window
2026-03-12 07:00:05 INFO     Weekly summary sent for 2026-03-05 to 2026-03-11
2026-03-12 11:02:00 WARNING  Pump appears to already be running at monitor start — duration will be measured from now
2026-03-12 11:05:03 ERROR    Unexpected error processing reading — continuing
```

When running in the background via the shell scripts, all output is written to `pumphouse_monitor.log` in the project root. The log file is overwritten each time the monitor starts.

| Level | When it appears |
|---|---|
| `INFO` | Startup, pump on/off transitions, confirmed treatments, weekly summary sent |
| `WARNING` | Missed treatment cycle, pump already running at startup, malformed packets |
| `ERROR` | Unexpected exceptions (monitor continues running) |

---

## Testing

Tests use [pytest](https://pytest.org) and require no network or hardware.

```bash
# Make sure your virtual environment is active, then:
pytest tests/ -v
```

The test suite covers:

| File | What is tested |
|---|---|
| `tests/test_database.py` | Table creation, inserts, bool→int conversion, autoincrement IDs |
| `tests/test_email_sender.py` | SMTP connection, login credentials, message headers and body |
| `tests/test_treatment_cycle.py` | `covers_hour` boundary conditions, `is_due` logic including None guard |
| `tests/test_data_receiver.py` | XML parsing (valid and malformed), pump state machine, treatment window accumulation, missed treatment alerts, date rollover, weekly summary, startup behaviour, exception recovery |

`DataReceiver` is tested without a real network socket — the socket is mocked so tests run offline and instantly.

---

## Database

Readings are stored in `PH_DATA` in the configured SQLite file:

| Column | Type | Description |
|---|---|---|
| `ID` | INTEGER | Auto-incrementing primary key |
| `UNIX_TIMESTAMP` | INTEGER | Reading time as Unix timestamp |
| `TIMESTAMP` | TEXT | Reading time as `YYYY-MM-DD HH:MM:SS` (UTC) |
| `WATTS` | REAL | Power reading in watts |
| `PUMP_ON` | INTEGER | `1` if pump was on (above threshold), `0` otherwise |
| `DURATION` | REAL | Minutes since last pump state change |

Included SQL helpers:

```bash
./scripts/show_last_20_rows.sh   # Last 20 readings
./scripts/show_pump_on.sh        # Readings where pump was on
```
