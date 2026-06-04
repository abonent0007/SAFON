"""
Модуль отправки email уведомлений — полноценный HTML-отчёт
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict

from .database import EVENT_CATEGORIES


def _safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode('ascii', errors='replace').decode('ascii'))


class EmailNotifier:
    def __init__(self, smtp_server: str, smtp_port: int, username: str, password: str):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password

    @staticmethod
    def from_env(env_vars: dict):
        return EmailNotifier(
            smtp_server=env_vars.get('SMTP_SERVER', 'smtp.gmail.com'),
            smtp_port=int(env_vars.get('SMTP_PORT', 587)),
            username=env_vars.get('SMTP_USERNAME', ''),
            password=env_vars.get('SMTP_PASSWORD', '')
        )

    def send_important_predictions(self, recipient: str, predictions: List[Dict]) -> bool:
        if not predictions or not self.username or not self.password:
            return False

        subject = f"SAFON — Important predictions ({len(predictions)} events)"

        colors = {
            'землетрясение': '#ff6600', 'цунами': '#0066ff',
            'наводнение': '#00ccff', 'пожар': '#ff4400',
            'ураган': '#44aaff', 'экономический кризис': '#ff8800',
            'война': '#ff0000', 'эпидемия': '#8800ff',
            'засуха': '#cc8800', 'революция': '#ff00ff',
            'экологическая катастрофа': '#22aa22',
        }

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        html_body = f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0a0e27;font-family:'Segoe UI',Arial,sans-serif;color:#fff;">
<div style="max-width:700px;margin:0 auto;padding:20px;">

<div style="text-align:center;padding:25px 0 15px;border-bottom:1px solid #2a2f4a;">
    <h1 style="margin:0;font-size:28px;letter-spacing:3px;">
        C.A.<span style="color:#00d4ff;">F</span>.O.<span style="color:#00d4ff;">N</span>.
    </h1>
    <p style="color:#8892b0;margin:8px 0 0;font-size:13px;">
        Fractal-Causal Autonomous Prediction System
    </p>
    <p style="color:#8892b0;margin:4px 0 0;font-size:11px;">
        Report generated: {now} | Horizon: 80 years | DeepSeek V4 Pro
    </p>
</div>

<div style="background:rgba(255,68,68,0.1);border-radius:8px;padding:15px;margin:20px 0;text-align:center;">
    <h2 style="margin:0 0 10px;font-size:18px;color:#ff4444;">KEY EVENTS (probability >= 70%)</h2>
    <p style="margin:0;color:#8892b0;font-size:12px;">{len(predictions)} high-probability events</p>
</div>
"""

        for p in predictions[:15]:
            cat = p.get('category', 'event')
            prob = int(p.get('probability', 0) * 100)
            pred_year = p.get('predicted_year', p.get('year', '????'))
            location = p.get('location', 'global')
            description = p.get('description', '')
            reasoning = p.get('reasoning', '')
            cat_color = colors.get(cat, '#00d4ff')
            cat_icon = EVENT_CATEGORIES.get(cat, {}).get('icon', '')
            prob_color = '#ff4444' if prob >= 80 else '#ffaa00' if prob >= 70 else '#ffcc66'

            html_body += f"""
<div style="background:rgba(30,35,60,0.9);border-radius:10px;padding:18px;margin:12px 0;border-left:4px solid {cat_color};">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;">
        <h3 style="margin:0;font-size:16px;">{cat_icon} {cat.upper()}</h3>
        <span style="font-size:22px;font-weight:bold;color:{prob_color};">{prob}%</span>
    </div>
    <p style="margin:8px 0 0;color:#00d4ff;font-size:14px;">
        Year: <strong>{pred_year}</strong> &nbsp;|&nbsp; Location: <strong>{location}</strong>
    </p>
    <div style="margin-top:10px;padding:12px;background:rgba(0,0,0,0.3);border-radius:6px;font-size:14px;line-height:1.5;color:#ccd6f6;">
        <p style="margin:0;color:#ffaa00;font-weight:bold;font-size:12px;">DESCRIPTION:</p>
        <p style="margin:4px 0 0;">{description}</p>
    </div>
    <div style="margin-top:8px;padding:10px;background:rgba(0,212,255,0.05);border-radius:6px;font-size:13px;line-height:1.4;color:#8892b0;">
        <p style="margin:0;color:#00d4ff;font-weight:bold;font-size:11px;">CYCLE ANALYSIS:</p>
        <p style="margin:4px 0 0;">{reasoning}</p>
    </div>
</div>
"""

        html_body += f"""
<div style="text-align:center;padding:20px;margin-top:20px;border-top:1px solid #2a2f4a;color:#8892b0;font-size:11px;">
    SAFON v4.0 | Autonomous Fractal-Causal Prediction System<br>
    DeepSeek V4 Pro | 80-year forecast horizon<br>
    {len(predictions)} high-probability events in this report
</div>

</div></body></html>"""

        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = self.username
        msg['To'] = recipient
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            _safe_print(f"Email sent to {recipient}")
            return True
        except Exception as e:
            _safe_print(f"Email error: {e}")
            return False
