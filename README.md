# Electricity Grid Monitor

A small Linux service that watches mains power, records electricity transitions in SQLite,
reports availability, produces PNG charts, and optionally sends email and Telegram alerts.

On this laptop the auto-detected source is `/sys/class/power_supply/AC/online`.

## Features

- Records the initial observation and every subsequent `ON`/`OFF` transition
- Keeps durable logs in SQLite with UTC timestamps
- Shows live status, history, outage count, and availability percentage
- Exports raw events to CSV and generates timeline/daily availability plots
- Serves a responsive local reporting dashboard without extra dependencies
- Enables or disables all alert delivery from the dashboard
- Sends multipart plain-text and HTML email through any SMTP provider
- Sends immediate outage and restoration messages through a Telegram bot
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

For Telegram, create a bot with [BotFather](https://t.me/BotFather), send the bot `/start`, and
configure its token and your chat ID:

```dotenv
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your-private-bot-token
TELEGRAM_CHAT_ID=your-chat-id
```

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

Explore the live report in a browser:

```bash
PYTHONPATH=. python3 -m grid_monitor serve
```

Open <http://127.0.0.1:8090>. The dashboard shows availability, outage duration, an interactive
period selector, the event timeline, recent transitions, and CSV downloads. It refreshes every
30 seconds. Manual runs are accessible only from this laptop by default; add `--host 0.0.0.0`
to expose them on the local network.

Supported periods use hours, days, or weeks, such as `12h`, `7d`, and `4w`.

Test SMTP after enabling and configuring notifications:

```bash
.venv/bin/grid-monitor test-email
```

Test Telegram after enabling and configuring that delivery channel:

```bash
.venv/bin/grid-monitor test-telegram
```

## Run At Startup

The installer creates and starts both `/etc/systemd/system/grid-monitor.service` and
`/etc/systemd/system/grid-monitor-dashboard.service`. The monitor and dashboard start at boot
and restart automatically after a failure. The installed dashboard listens on all network
interfaces at port `8090`, so any device on the same network can open
`http://LAPTOP_IP_ADDRESS:8090`. Configure `DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD` before
exposing it outside a trusted local network. Run the script as your regular user; it requests
`sudo` only for system service operations.

```bash
chmod +x scripts/install-service.sh
./scripts/install-service.sh
sudo systemctl status grid-monitor
sudo systemctl status grid-monitor-dashboard
sudo journalctl -u grid-monitor -f
```

Restart the service after changing `.env`:

```bash
sudo systemctl restart grid-monitor
```

If system-wide service installation is unavailable, install only the dashboard for the current
Linux user without sudo:

```bash
chmod +x scripts/install-user-dashboard.sh
./scripts/install-user-dashboard.sh
systemctl --user status grid-monitor-dashboard-user
```

## Cloudflare Tunnel

The optional Cloudflare connector publishes the local dashboard through an outbound tunnel. Its
user service restarts automatically and does not require router port forwarding. Put the named
tunnel UUID in `CLOUDFLARE_TUNNEL_ID` inside `.env`, then run:

```bash
chmod +x scripts/install-cloudflare-tunnel.sh
./scripts/install-cloudflare-tunnel.sh
systemctl --user status cloudflare-grid-tunnel
```

The Cloudflare DNS route and Access application must point the chosen public hostname to the
`electricity-grid-monitor` tunnel and `http://127.0.0.1:8090` origin.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_PATH` | `data/grid_monitor.db` | SQLite event database |
| `POLL_INTERVAL_SECONDS` | `5` | Time between checks |
| `POWER_SUPPLY_PATH` | auto-detected | Supply directory or `online` file |
| `SITE_NAME` | `Home Grid` | Location shown in reports and email |
| `TZ` | system timezone | Email display timezone |
| `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD` | empty | Optional HTTP Basic authentication |
| `BATTERY_WARNING_PERCENT` | `15` | Dashboard warning level; does not trigger shutdown |
| `CLOUDFLARE_TUNNEL_ID` | empty | Optional named Cloudflare Tunnel UUID |
| `NOTIFICATION_ENABLED` | `false` | Master alert switch, also controlled by the dashboard |
| `EMAIL_NOTIFICATION_ENABLED` | `true` | Enable the email delivery channel |
| `SMTP_HOST`, `SMTP_PORT` | empty, `587` | SMTP endpoint |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | empty | Optional SMTP authentication |
| `SMTP_FROM_EMAIL` | empty | Sender address |
| `NOTIFICATION_TO_EMAIL` | empty | Alert recipient |
| `SMTP_USE_TLS` | `true` | Upgrade SMTP with STARTTLS |
| `SMTP_USE_SSL` | `false` | Use implicit TLS instead |
| `TELEGRAM_ENABLED` | `false` | Enable the Telegram delivery channel |
| `TELEGRAM_BOT_TOKEN` | empty | Private token issued by BotFather |
| `TELEGRAM_CHAT_ID` | empty | User, group, or channel receiving alerts |

`SMTP_USE_TLS` and `SMTP_USE_SSL` cannot both be true.

## Data Model

The `power_events` table contains `timestamp`, `state`, `source`, and `reason`. An `initial`
record establishes the first known state. A `transition` record represents detected electricity
loss or restoration. Polling records transitions rather than creating duplicate rows every five
seconds.
