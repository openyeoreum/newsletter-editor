import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from .base import SendResult, personalize
from .. import config


class MailHogSender:
    def send(self, html, subject, recipients, from_addr, from_name="전인교육학회", on_progress=None):
        result = SendResult()
        try:
            with smtplib.SMTP(config.MAILHOG_HOST, config.MAILHOG_PORT) as s:
                for r in recipients:
                    try:
                        msg = MIMEMultipart("alternative")
                        msg["Subject"] = subject
                        msg["From"] = formataddr((from_name, from_addr or "noreply@local"))
                        msg["To"] = formataddr((r.name or "", r.email))
                        msg.attach(MIMEText(personalize(html, r.email), "html", "utf-8"))
                        s.sendmail(from_addr or "noreply@local", [r.email], msg.as_string())
                        result.sent += 1
                    except Exception as e:
                        result.failed += 1
                        result.errors.append(f"{r.email}: {e}")
                    if on_progress:
                        on_progress(sent=result.sent, failed=result.failed)
        except Exception as e:
            result.errors.append(f"MailHog: {e}")
            result.failed = len(recipients) - result.sent
        return result
