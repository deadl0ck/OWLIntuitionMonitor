# OWL Intuition Power Monitor

Listens for UDP multicast data from an OWL Intuition power monitor and tracks electricity usage to a local SQLite database. When a monitored circuit (e.g. a pumphouse pump) runs longer than a configurable threshold, an alert email is sent via Gmail.

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
# Edit config.ini — set your email addresses, threshold, etc.

# 6. Run
python3 main.py
```

---

## How it works

The OWL Intuition device broadcasts power readings as XML over UDP multicast. This tool:
- Joins the multicast group and receives readings continuously
- Detects when power on the monitored channel crosses 1000 W (pump on/off)
- Records every reading to a SQLite database
- Emails an alert if the pump runs longer than `alarm_threshold_minutes`
- Emails again when a long run finishes, reporting the total duration
- Sends a startup confirmation email when the monitor begins

---

## Directory structure

```
OWLIntuitionMonitor/
├── main.py               # Entry point — loads config and starts the receiver
├── config.ini            # Application settings (port, email, threshold)
├── .env.example          # Template for secrets — copy to .env and fill in
├── requirements.txt      # Python dependencies
│
├── monitor/              # Core application package
│   ├── database.py       # SQLite interface (creates table, inserts readings)
│   ├── data_receiver.py  # UDP multicast listener and pump state machine
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
    └── test_email_sender.py
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
| `[network] multicast_port` | OWL Intuition multicast port (default: `22600`) |
| `[database] filename` | SQLite database file path |
| `[email] sender` | Gmail address used to send alerts |
| `[email] receiver` | Email address to receive alerts |
| `[monitor] alarm_threshold_minutes` | Minutes of continuous high usage before alerting |

---

## Running

```bash
# Foreground (output to terminal)
python3 main.py

# Background — logs to pumphouse_monitor.log
./scripts/monitor_pumphouse.sh

# Restart a running instance
./scripts/restart_monitor.sh

# Check if the monitor is running
./scripts/show_monitor_process.sh
```

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
| `tests/test_data_receiver.py` | XML parsing (valid and malformed), pump state machine, threshold alerting, email deduplication |

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
| `PUMP_ON` | INTEGER | `1` if pump was on (>1000 W), `0` otherwise |
| `DURATION` | REAL | Minutes since last pump state change |

Included SQL helpers:

```bash
./show_last_20_rows.sh   # Last 20 readings
./show_pump_on.sh        # Readings where pump was on
```
