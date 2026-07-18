from __future__ import annotations

import csv
import base64
import binascii
import hmac
import html
import io
import logging
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import PowerEvent, PowerState
from .reporting import events_with_context, parse_period, summarize
from .storage import EventStore


PERIODS = ("24h", "7d", "30d", "12w")


def authorization_valid(header: str | None, username: str, password: str) -> bool:
    if not username and not password:
        return True
    if not header or not header.startswith("Basic "):
        return False
    try:
        supplied = base64.b64decode(header[6:], validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    return hmac.compare_digest(supplied, f"{username}:{password}")


def format_duration(seconds: float) -> str:
    total_minutes = max(0, round(seconds / 60))
    days, remaining = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remaining, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def display_timezone(name: str):
    if not name:
        return datetime.now().astimezone().tzinfo or timezone.utc
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return timezone.utc


def timeline_svg(events: list[PowerEvent], start: datetime, end: datetime) -> str:
    if not events:
        return '<div class="empty">No observations in this period</div>'

    width = 1000
    duration = max((end - start).total_seconds(), 1)
    parts = [
        f'<svg class="timeline" viewBox="0 0 {width} 72" role="img" '
        'aria-label="Electricity availability timeline">',
        '<rect x="0" y="12" width="1000" height="36" rx="4" fill="#e8ecea"/>',
    ]
    for index, event in enumerate(events):
        segment_start = max(start, event.timestamp)
        segment_end = min(end, events[index + 1].timestamp if index + 1 < len(events) else end)
        if segment_end <= segment_start:
            continue
        x = (segment_start - start).total_seconds() / duration * width
        segment_width = max((segment_end - segment_start).total_seconds() / duration * width, 1)
        color = "#16734b" if event.state is PowerState.ON else "#cf3d32"
        label = "Available" if event.state is PowerState.ON else "Outage"
        parts.append(
            f'<rect x="{x:.2f}" y="12" width="{segment_width:.2f}" height="36" '
            f'fill="{color}"><title>{label}: {segment_start.isoformat()}</title></rect>'
        )
    parts.extend(
        [
            '<text x="0" y="67">Period start</text>',
            '<text x="1000" y="67" text-anchor="end">Now</text>',
            "</svg>",
        ]
    )
    return "".join(parts)


def outage_pattern(
    events: list[PowerEvent], start: datetime, end: datetime, tz
) -> list[list[tuple[float, float] | None]]:
    """Aggregate observed and outage seconds into local weekday/hour slots."""
    observed = [[0.0 for _ in range(24)] for _ in range(7)]
    outages = [[0.0 for _ in range(24)] for _ in range(7)]
    for index, event in enumerate(events):
        segment_start = max(start, event.timestamp)
        segment_end = min(end, events[index + 1].timestamp if index + 1 < len(events) else end)
        cursor = segment_start
        while cursor < segment_end:
            next_hour = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            piece_end = min(segment_end, next_hour)
            seconds = (piece_end - cursor).total_seconds()
            local = cursor.astimezone(tz)
            observed[local.weekday()][local.hour] += seconds
            if event.state is PowerState.OFF:
                outages[local.weekday()][local.hour] += seconds
            cursor = piece_end

    result: list[list[tuple[float, float] | None]] = []
    for weekday in range(7):
        row = []
        for hour in range(24):
            seconds = observed[weekday][hour]
            row.append((outages[weekday][hour] / seconds * 100, seconds) if seconds else None)
        result.append(row)
    return result


def pattern_chart(events: list[PowerEvent], start: datetime, end: datetime, tz) -> str:
    weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    pattern = outage_pattern(events, start, end, tz)
    if not any(cell is not None for row in pattern for cell in row):
        return '<div class="empty">No observations available for pattern analysis</div>'

    headings = "".join(f"<th>{hour:02d}</th>" for hour in range(24))
    rows = []
    for weekday, values in zip(weekdays, pattern):
        cells = []
        for hour, value in enumerate(values):
            if value is None:
                cells.append(
                    f'<td class="heat no-data" title="{weekday} {hour:02d}:00: not observed"></td>'
                )
                continue
            percentage, observed_seconds = value
            level = 0 if percentage == 0 else 1 if percentage < 10 else 2 if percentage < 30 else 3 if percentage < 60 else 4
            detail = (
                f"{weekday} {hour:02d}:00-{(hour + 1) % 24:02d}:00: "
                f"{percentage:.1f}% outage over {format_duration(observed_seconds)} observed"
            )
            cells.append(
                f'<td class="heat heat-{level}" title="{html.escape(detail)}">'
                f'<span class="sr-only">{html.escape(detail)}</span></td>'
            )
        rows.append(f'<tr><th class="weekday">{weekday[:3]}</th>{"".join(cells)}</tr>')
    return (
        '<div class="heatmap-wrap"><table class="heatmap" aria-label="Outage percentage by weekday and hour">'
        f'<thead><tr><th class="weekday">Day</th>{headings}</tr></thead><tbody>{"".join(rows)}</tbody>'
        '</table></div><div class="heat-legend"><span>Less outage</span>'
        '<i class="heat-0"></i><i class="heat-1"></i><i class="heat-2"></i><i class="heat-3"></i><i class="heat-4"></i>'
        '<span>More outage</span><i class="no-data"></i><span>Not observed</span></div>'
    )


def render_dashboard(
    store: EventStore,
    site_name: str,
    period: str,
    timezone_name: str,
    now: datetime | None = None,
) -> str:
    if period not in PERIODS:
        period = "7d"
    start, end = parse_period(period, now)
    summary = summarize(store, start, end)
    context_events = events_with_context(store, start, end)
    recent = store.list_events(start=start, end=end, limit=50, descending=True)
    tz = display_timezone(timezone_name)
    current = summary.current_state
    status_class = "online" if current is PowerState.ON else "offline" if current else "unknown"
    status_label = "Grid available" if current is PowerState.ON else "Power outage" if current else "Unknown"

    period_links = "".join(
        f'<a class="period {"active" if item == period else ""}" href="/?period={item}">{item}</a>'
        for item in PERIODS
    )
    rows = []
    for event in recent:
        local_time = event.timestamp.astimezone(tz)
        state_label = "Available" if event.state is PowerState.ON else "Outage"
        rows.append(
            "<tr>"
            f'<td><span class="event-dot {event.state.value}"></span>{state_label}</td>'
            f'<td>{html.escape(local_time.strftime("%b %d, %Y %H:%M:%S %Z"))}</td>'
            f"<td>{html.escape(event.reason.title())}</td>"
            f"<td class=\"source\">{html.escape(event.source)}</td>"
            "</tr>"
        )
    table_body = "".join(rows) or '<tr><td colspan="4" class="empty-cell">No transitions recorded</td></tr>'
    observed_note = (
        f"Based on {format_duration(summary.observed_seconds)} observed"
        if summary.observed_seconds
        else "Waiting for the first observation"
    )
    availability = f"{summary.availability_percent:.2f}%" if summary.observed_seconds else "--"
    updated = end.astimezone(tz).strftime("%b %d, %Y %H:%M:%S %Z")
    pattern = pattern_chart(context_events, start, end, tz)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="30">
  <title>{html.escape(site_name)} | Grid report</title>
  <style>
    :root {{ color-scheme: light; --ink:#18221e; --muted:#66736d; --line:#dce3df; --surface:#fff; --page:#f4f6f5; --green:#16734b; --red:#cf3d32; --blue:#236899; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--page); color:var(--ink); font:14px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; letter-spacing:0; }}
    header {{ background:#17241e; color:#fff; }}
    .header-inner,.content {{ width:min(1180px,calc(100% - 32px)); margin:auto; }}
    .header-inner {{ min-height:70px; display:flex; align-items:center; justify-content:space-between; gap:20px; }}
    h1 {{ margin:0; font-size:20px; font-weight:650; letter-spacing:0; }}
    .subtitle {{ color:#b8c5bf; font-size:12px; }}
    .status {{ display:inline-flex; align-items:center; gap:8px; font-weight:650; }}
    .status::before {{ content:""; width:9px; height:9px; border-radius:50%; background:#98a39e; box-shadow:0 0 0 3px #ffffff18; }}
    .status.online::before {{ background:#56d292; }} .status.offline::before {{ background:#ff7066; }}
    .toolbar {{ display:flex; justify-content:space-between; align-items:center; gap:16px; padding:24px 0 16px; }}
    .periods {{ display:flex; border:1px solid var(--line); background:#fff; border-radius:6px; overflow:hidden; }}
    .period {{ padding:7px 12px; color:var(--muted); text-decoration:none; border-right:1px solid var(--line); }}
    .period:last-child {{ border:0; }} .period.active {{ background:#243f33; color:#fff; }}
    .export {{ color:var(--blue); font-weight:600; text-decoration:none; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); border:1px solid var(--line); border-radius:6px; background:var(--surface); }}
    .metric {{ padding:18px 20px; border-right:1px solid var(--line); min-width:0; }} .metric:last-child {{ border:0; }}
    .metric-label {{ color:var(--muted); font-size:12px; }} .metric-value {{ margin-top:3px; font-size:25px; font-weight:680; white-space:nowrap; }}
    .metric-detail {{ color:var(--muted); font-size:11px; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    section {{ margin-top:18px; padding:20px; background:var(--surface); border:1px solid var(--line); border-radius:6px; }}
    .section-head {{ display:flex; justify-content:space-between; gap:16px; align-items:baseline; margin-bottom:15px; }}
    h2 {{ margin:0; font-size:15px; font-weight:680; }} .legend {{ display:flex; gap:14px; color:var(--muted); font-size:12px; }}
    .key::before {{ content:""; display:inline-block; width:8px; height:8px; margin-right:5px; border-radius:2px; background:var(--green); }} .key.off::before {{ background:var(--red); }}
    .timeline {{ display:block; width:100%; height:auto; overflow:visible; }} .timeline text {{ fill:var(--muted); font-size:11px; }}
    .empty {{ height:72px; display:grid; place-items:center; color:var(--muted); background:#f7f9f8; }}
    .heatmap-wrap {{ overflow-x:auto; padding-bottom:4px; }} .heatmap {{ border-collapse:separate; border-spacing:3px; width:100%; min-width:820px; table-layout:fixed; }}
    .heatmap th {{ padding:2px 0; border:0; text-align:center; font-size:10px; font-weight:550; color:var(--muted); }} .heatmap .weekday {{ width:38px; text-align:left; }}
    .heat {{ height:27px; padding:0; border:0; border-radius:2px; background:#dfe8e3; }} .heat-0 {{ background:#d7e7df; }} .heat-1 {{ background:#f2c7ae; }} .heat-2 {{ background:#e99772; }} .heat-3 {{ background:#d75c48; }} .heat-4 {{ background:#9e2f2b; }} .no-data {{ background:#edf0ee; background-image:repeating-linear-gradient(135deg,transparent,transparent 3px,#dfe4e1 3px,#dfe4e1 4px); }}
    .heat-legend {{ display:flex; align-items:center; justify-content:flex-end; gap:5px; margin-top:10px; color:var(--muted); font-size:11px; }} .heat-legend i {{ display:block; width:18px; height:12px; border-radius:2px; }} .heat-legend .no-data {{ margin-left:12px; }}
    .sr-only {{ position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }}
    .table-wrap {{ overflow-x:auto; }} table {{ border-collapse:collapse; width:100%; min-width:640px; }}
    th {{ color:var(--muted); font-size:11px; text-align:left; text-transform:uppercase; font-weight:650; }} th,td {{ padding:10px 8px; border-bottom:1px solid #edf0ee; }} tbody tr:last-child td {{ border-bottom:0; }}
    .event-dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--green); margin-right:8px; }} .event-dot.off {{ background:var(--red); }} .source {{ color:var(--muted); font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:12px; }}
    .empty-cell {{ text-align:center; color:var(--muted); padding:30px; }} footer {{ color:var(--muted); font-size:11px; padding:16px 0 28px; }}
    @media (max-width:760px) {{ .header-inner {{ min-height:64px; }} .metrics {{ grid-template-columns:1fr 1fr; }} .metric:nth-child(2) {{ border-right:0; }} .metric:nth-child(-n+2) {{ border-bottom:1px solid var(--line); }} .toolbar {{ align-items:flex-end; }} .metric-value {{ font-size:21px; }} }}
    @media (max-width:440px) {{ .header-inner,.content {{ width:min(100% - 20px,1180px); }} .subtitle {{ display:none; }} .period {{ padding:7px 9px; }} .export {{ font-size:0; }} .export::after {{ content:"CSV"; font-size:12px; }} .metric {{ padding:14px; }} section {{ padding:14px; }} }}
  </style>
</head>
<body>
  <header><div class="header-inner"><div><h1>{html.escape(site_name)}</h1><div class="subtitle">Electricity grid monitoring</div></div><div class="status {status_class}">{status_label}</div></div></header>
  <main class="content">
    <div class="toolbar"><nav class="periods" aria-label="Report period">{period_links}</nav><a class="export" href="/events.csv?period={period}">Download CSV</a></div>
    <div class="metrics">
      <div class="metric"><div class="metric-label">Availability</div><div class="metric-value">{availability}</div><div class="metric-detail">{observed_note}</div></div>
      <div class="metric"><div class="metric-label">Power available</div><div class="metric-value">{format_duration(summary.online_seconds)}</div><div class="metric-detail">Within observed time</div></div>
      <div class="metric"><div class="metric-label">Power unavailable</div><div class="metric-value">{format_duration(summary.outage_seconds)}</div><div class="metric-detail">Total outage duration</div></div>
      <div class="metric"><div class="metric-label">Outages detected</div><div class="metric-value">{summary.outage_count}</div><div class="metric-detail">Transitions in selected period</div></div>
    </div>
    <section><div class="section-head"><h2>Availability timeline</h2><div class="legend"><span class="key">Available</span><span class="key off">Outage</span></div></div>{timeline_svg(context_events, start, end)}</section>
    <section><div class="section-head"><h2>Outage pattern by day and hour</h2><span class="subtitle">Local time · selected period</span></div>{pattern}</section>
    <section><div class="section-head"><h2>Event history</h2><span class="subtitle">Latest 50 events</span></div><div class="table-wrap"><table><thead><tr><th>State</th><th>Local time</th><th>Type</th><th>Source</th></tr></thead><tbody>{table_body}</tbody></table></div></section>
    <footer>Last refreshed {html.escape(updated)} · Refreshes every 30 seconds</footer>
  </main>
</body>
</html>"""


def csv_response(store: EventStore, period: str, now: datetime | None = None) -> bytes:
    if period not in PERIODS:
        period = "7d"
    start, end = parse_period(period, now)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["id", "timestamp", "state", "source", "reason"])
    for event in store.list_events(start=start, end=end):
        writer.writerow([event.event_id, event.timestamp.isoformat(), event.state.value, event.source, event.reason])
    return output.getvalue().encode("utf-8")


def make_handler(
    store: EventStore,
    site_name: str,
    timezone_name: str,
    username: str = "",
    password: str = "",
):
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            request = urlparse(self.path)
            query = parse_qs(request.query)
            period = query.get("period", ["7d"])[0]
            period = period if period in PERIODS else "7d"
            if request.path == "/favicon.ico":
                self.send_content(204, "image/x-icon", b"")
                return
            if request.path != "/health" and not authorization_valid(
                self.headers.get("Authorization"), username, password
            ):
                body = b"Authentication required\n"
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="Grid Monitor", charset="UTF-8"')
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_common_headers(len(body))
                self.end_headers()
                self.wfile.write(body)
                return
            if request.path == "/":
                body = render_dashboard(store, site_name, period, timezone_name).encode("utf-8")
                self.send_content(200, "text/html; charset=utf-8", body)
                return
            if request.path == "/events.csv":
                body = csv_response(store, period)
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="grid-events-{period}.csv"')
                self.send_common_headers(len(body))
                self.end_headers()
                self.wfile.write(body)
                return
            if request.path == "/health":
                self.send_content(200, "text/plain; charset=utf-8", b"ok\n")
                return
            self.send_content(404, "text/plain; charset=utf-8", b"Not found\n")

        def send_content(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_common_headers(len(body))
            self.end_headers()
            self.wfile.write(body)

        def send_common_headers(self, content_length: int) -> None:
            self.send_header("Content-Length", str(content_length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'")

        def log_message(self, message: str, *args: object) -> None:
            logging.info("Dashboard: " + message, *args)

    return DashboardHandler


def serve_dashboard(
    store: EventStore,
    site_name: str,
    timezone_name: str,
    host: str = "127.0.0.1",
    port: int = 8090,
    username: str = "",
    password: str = "",
) -> None:
    server = ThreadingHTTPServer(
        (host, port), make_handler(store, site_name, timezone_name, username, password)
    )
    logging.info("Reporting dashboard available at http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Stopping reporting dashboard")
    finally:
        server.server_close()
