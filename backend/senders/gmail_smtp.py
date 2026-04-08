import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from .base import Recipient, SendResult, personalize
from .. import config


class GmailSender:
    def send(self, html, subject, recipients, from_addr, from_name="전인교육학회"):
        result = SendResult()
        user = config.GMAIL_USER or from_addr
        pw = config.GMAIL_APP_PASSWORD
        if not pw:
            result.errors.append("GMAIL_APP_PASSWORD not set in .env")
            result.failed = len(recipients)
            return result
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
                s.login(user, pw)
                for r in recipients:
                    try:
                        msg = MIMEMultipart("alternative")
                        msg["Subject"] = subject
                        msg["From"] = formataddr((from_name, user))
                        msg["To"] = formataddr((r.name or "", r.email))
                        msg.attach(MIMEText(personalize(html, r.email), "html", "utf-8"))
                        s.sendmail(user, [r.email], msg.as_string())
                        result.sent += 1
                    except Exception as e:
                        result.failed += 1
                        result.errors.append(f"{r.email}: {e}")
        except Exception as e:
            result.errors.append(f"SMTP: {e}")
            result.failed = len(recipients) - result.sent
        return result
