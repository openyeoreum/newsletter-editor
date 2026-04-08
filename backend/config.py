import os
from dotenv import load_dotenv

load_dotenv()

# Gmail SMTP
GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

# MailHog (로컬 테스트)
MAILHOG_HOST = os.getenv("MAILHOG_HOST", "mailhog")
MAILHOG_PORT = int(os.getenv("MAILHOG_PORT", "1025"))

# NCP Cloud Outbound Mailer
NCP_ACCESS_KEY = os.getenv("NCP_ACCESS_KEY", "")
NCP_SECRET_KEY = os.getenv("NCP_SECRET_KEY", "")
NCP_SENDER_ADDRESS = os.getenv("NCP_SENDER_ADDRESS", "")
NCP_SENDER_NAME = os.getenv("NCP_SENDER_NAME", "전인교육학회")

# Cloudinary
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")

DRAFTS_DIR = os.getenv("DRAFTS_DIR", "/data/drafts")
TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", "/app/templates")
RECIPIENTS_DIR = os.getenv("RECIPIENTS_DIR", "/data/recipients")
UNSUBSCRIBED_FILE = os.getenv("UNSUBSCRIBED_FILE", "/data/recipients/unsubscribed.csv")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
