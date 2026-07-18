from __future__ import annotations

import html
import smtplib
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings
from .models import PowerEvent, PowerState


def display_time(timestamp: datetime, timezone_name: str) -> str:
    if timezone_name:
        try:
            timestamp = timestamp.astimezone(ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown TZ value: {timezone_name}") from exc
    return timestamp.strftime("%A, %B %d, %Y at %I:%M:%S %p %Z")


def build_message(event: PowerEvent, settings: Settings) -> EmailMessage:
    is_on = event.state is PowerState.ON
    accent = "#138a52" if is_on else "#c83b3b"
    badge_background = "#e8f7ef" if is_on else "#fff0f0"
    icon = "&#9889;" if is_on else "&#9888;"
    headline = "Electricity has been restored" if is_on else "A power outage was detected"
    detail = (
        "Mains power is available again. The monitor will continue watching for changes."
        if is_on
        else "Mains power is unavailable. This alert was sent while the monitoring device remained online."
    )
    when = display_time(event.timestamp, settings.timezone)
    site = html.escape(settings.site_name)

    message = EmailMessage()
    message["Subject"] = f"{event.state.label} - {settings.site_name}"
    message["From"] = settings.smtp_from_email
    message["To"] = settings.notification_to_email
    message.set_content(
        f"{headline}\n\nLocation: {settings.site_name}\nTime: {when}\n"
        f"Source: {event.source}\n\n{detail}"
    )
    message.add_alternative(
        f"""\
<!doctype html>
<html lang="en">
  <body style="margin:0;background:#f3f5f7;font-family:Arial,sans-serif;color:#20262d">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f5f7;padding:32px 12px">
      <tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#ffffff;border:1px solid #dde2e7;border-radius:8px;overflow:hidden">
          <tr><td style="height:6px;background:{accent}"></td></tr>
          <tr><td style="padding:36px 40px 18px">
            <div style="display:inline-block;padding:8px 12px;background:{badge_background};color:{accent};border-radius:6px;font-size:14px;font-weight:bold">{icon} {html.escape(event.state.label)}</div>
            <h1 style="margin:22px 0 10px;font-size:26px;line-height:1.25;color:#151a1f">{headline}</h1>
            <p style="margin:0;color:#58616b;font-size:16px;line-height:1.6">{detail}</p>
          </td></tr>
          <tr><td style="padding:10px 40px 34px">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f7f8f9;border:1px solid #e5e8eb;border-radius:6px">
              <tr><td style="padding:18px 20px 7px;color:#737c85;font-size:12px;text-transform:uppercase">Location</td></tr>
              <tr><td style="padding:0 20px 14px;font-size:16px;font-weight:bold">{site}</td></tr>
              <tr><td style="padding:14px 20px 7px;border-top:1px solid #e5e8eb;color:#737c85;font-size:12px;text-transform:uppercase">Detected at</td></tr>
              <tr><td style="padding:0 20px 18px;font-size:16px">{html.escape(when)}</td></tr>
            </table>
          </td></tr>
          <tr><td style="padding:18px 40px;background:#20262d;color:#bec5cc;font-size:12px;line-height:1.5">Automated alert from {site} Electricity Grid Monitor</td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>
""",
        subtype="html",
    )
    return message


def send_notification(event: PowerEvent, settings: Settings) -> None:
    message = build_message(event, settings)
    smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
    with smtp_class(settings.smtp_host, settings.smtp_port, timeout=30) as client:
        if settings.smtp_use_tls:
            client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)

