# OWL Intuition Pumphouse Monitor — Claude Context

## What this project does

Listens for UDP multicast data from an OWL Intuition power monitor and tracks a pumphouse pump.
Sends alert emails when water treatment cycles are missed, when unexpected runs occur, and on startup.
Stores all readings in a local SQLite database (`pumphouse.db`).

## Environment

- Runs on a Raspberry Pi with DietPi, SSD at `/mnt/ssd/git/OWLIntuitionMonitor/`
- Systemd service: `pumphouse-monitor.service`, runs as user `martin`
- Python venv at `.venv/`, secrets in `.env` (gitignored)
- Logs: `sudo journalctl -u pumphouse-monitor.service -f`

## Key config (config.ini)

- `pump_threshold_watts = 1000` — watts above which pump is considered on
- `unexpected_alert_threshold_minutes = 7`
- Current treatment cycles (BST, UTC+1, late Mar–late Oct):
  ```
  cycles = 14,0,1,15,14-night | 5,1,3,3,5-night | 3,3,4,8,3-night
  ```
  Format: `interval_days,utc_start_hour,utc_end_hour,min_duration_minutes,label`
- **IMPORTANT:** When clocks change (BST↔GMT), the UTC hours in `cycles` must be adjusted by ±1 hour.
  GMT (winter) equivalent is noted in a comment in `config.ini`.
- `send_confirmation_emails = true` — disable once schedule is confirmed stable

## Treatment cycles (current BST windows)

| Cycle | UTC window | Min duration | Runs every |
|---|---|---|---|
| 14-night | 00:00–01:00 | 15 min | 14 days |
| 5-night | 01:00–03:00 | 3 min | 5 days |
| 3-night | 03:00–04:00 | 8 min | 3 days |

## Database

File: `pumphouse.db`, table: `PH_DATA`

| Column | Description |
|---|---|
| TIMESTAMP | UTC datetime (YYYY-MM-DD HH:MM:SS) |
| WATTS | Power reading |
| PUMP_ON | 1 if pump on (above threshold), 0 otherwise |
| DURATION | Minutes since last pump state change |

Useful query to check a treatment window:
```sql
SELECT TIMESTAMP, WATTS, PUMP_ON, ROUND(DURATION,2) FROM PH_DATA
WHERE TIMESTAMP >= '2026-MM-DD HH:00:00' AND TIMESTAMP < '2026-MM-DD HH:00:00'
ORDER BY TIMESTAMP;
```

## Known behaviour / gotchas

### OWL device can go silent for hours
The OWL Intuition device occasionally stops broadcasting UDP packets for extended periods (observed:
~5 hours on the night of 2026-05-28/29). The monitor service keeps running (no crash) but writes
nothing to the database during the gap. This can cause false-positive missed-treatment alerts if
a treatment window falls entirely within the silence period.

**How to diagnose:** If you see a missed-treatment alert but the pump was clearly running (e.g.
DURATION on the first post-gap reading is very large), check `journalctl` to confirm the service
never restarted — that confirms the OWL went silent, not the pump.

### Carry-over pump runs not counted in windows
If the pump is already running when a treatment window opens, the in-window accumulator only
counts from the first received reading inside the window onwards. A pump run that started hours
before the window and stopped 14 minutes in may only register ~0.4 min if the OWL was silent
for the early part of the window.

### DURATION on first post-gap reading
After an OWL silence, the first PUMP_ON=1 reading will show a very large DURATION (e.g. 317 min).
This is the elapsed time since the last database entry, not a real pump-on duration in the window.

## Recent alert history

| Date | Alert | Verdict |
|---|---|---|
| 2026-05-29 | Missed 3-night treatment | **False positive** — OWL device was silent ~21:57 May 28 to ~03:13 May 29 (~5 hrs). Pump ran continuously through the window. |
| 2026-05-30 | Missed 5-night treatment (UTC 01:00–03:00) | **Genuine miss** — no pump activity in window (confirmed from DB: 3 readings, all PUMP_ON=0). Treatment did not run. |

## Running / management

```bash
# Service status
sudo systemctl status pumphouse-monitor.service

# Restart
sudo systemctl restart pumphouse-monitor.service

# Live logs
sudo journalctl -u pumphouse-monitor.service -f

# Run tests
source .venv/bin/activate && pytest tests/ -v
```
