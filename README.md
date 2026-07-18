# Electricity Grid Monitor

A small Linux service that watches mains power, records electricity transitions in SQLite,
reports availability, produces PNG charts, and optionally sends responsive HTML email alerts.

On this laptop the auto-detected source is `/sys/class/power_supply/AC/online`.

## Features

- Records the initial observation and every subsequent `ON`/`OFF` transition
- Keeps durable logs in SQLite with UTC timestamps
- Shows live status, history, outage count, and availability percentage
- Exports raw events to CSV and generates timeline/daily availability plots
- Enables or disables email with `NOTIFICATION_ENABLED`
- Sends multipart plain-text and HTML email through any SMTP provider
- Runs continuously as a hardened systemd service

## Requirements

- Linux with a mains supply exposed under `/sys/class/power_supply`
- Python 3.11 or newer
- Matplotlib only for the `plot` command

The laptop battery keeps the monitor alive during an outage. To send an outage email in real
time, the network connection must also stay online; use a UPS-backed router or cellular data.
A computer that loses all power cannot observe the outage until it starts again.

## Setup

```bash
cd /home/shampad/Desktop/projects/electricity-grid-monitor
sudo apt install python3-venv
python3 -m venv .venv
.venv/bin/pip install -e '.[plot]'
cp .env.example .env
```

The monitor, history, summary, CSV, and email commands use only Python's standard library. If
you do not need PNG charts, you can skip the virtual environment and run commands as
`PYTHONPATH=. python3 -m grid_monitor <command>`. The systemd service uses this dependency-free
form.

Edit `.env`. Monitoring works with the defaults. For email, provide the SMTP values and set:

```dotenv
NOTIFICATION_ENABLED=true
```

For Gmail, use an app password rather than the account password. Keep `.env` private; it is
excluded from Git.

## Use

Check the live input and configuration:

```bash
.venv/bin/grid-monitor status
```

Run one observation, then start continuous monitoring:

```bash
.venv/bin/grid-monitor check
.venv/bin/grid-monitor monitor
```

Query and report the stored data:

```bash
.venv/bin/grid-monitor history --limit 30
.venv/bin/grid-monitor summary --period 7d
.venv/bin/grid-monitor export --period 30d --output reports/month.csv
.venv/bin/grid-monitor plot --period 7d --output reports/week.png
```

Supported periods use hours, days, or weeks, such as `12h`, `7d`, and `4w`.

Test SMTP after enabling and configuring notifications:

```bash
.venv/bin/grid-monitor test-email
```

## Run At Startup

The installer creates and starts `/etc/systemd/system/grid-monitor.service`. Run the script as
your regular user; it requests `sudo` only for system service operations.

```bash
chmod +x scripts/install-service.sh
./scripts/install-service.sh
sudo systemctl status grid-monitor
sudo journalctl -u grid-monitor -f
```

Restart the service after changing `.env`:

```bash
sudo systemctl restart grid-monitor
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_PATH` | `data/grid_monitor.db` | SQLite event database |
| `POLL_INTERVAL_SECONDS` | `5` | Time between checks |
| `POWER_SUPPLY_PATH` | auto-detected | Supply directory or `online` file |
| `SITE_NAME` | `Home Grid` | Location shown in reports and email |
| `TZ` | system timezone | Email display timezone |
| `NOTIFICATION_ENABLED` | `false` | Email feature flag |
| `SMTP_HOST`, `SMTP_PORT` | empty, `587` | SMTP endpoint |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | empty | Optional SMTP authentication |
| `SMTP_FROM_EMAIL` | empty | Sender address |
| `NOTIFICATION_TO_EMAIL` | empty | Alert recipient |
| `SMTP_USE_TLS` | `true` | Upgrade SMTP with STARTTLS |
| `SMTP_USE_SSL` | `false` | Use implicit TLS instead |

`SMTP_USE_TLS` and `SMTP_USE_SSL` cannot both be true.

## Data Model

The `power_events` table contains `timestamp`, `state`, `source`, and `reason`. An `initial`
record establishes the first known state. A `transition` record represents detected electricity
loss or restoration. Polling records transitions rather than creating duplicate rows every five
seconds.
