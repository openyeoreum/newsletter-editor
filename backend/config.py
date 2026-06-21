import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _default_path(env_name: str, local_path: str, docker_path: str) -> str:
    value = os.getenv(env_name)
    if value:
        return value
    local = PROJECT_ROOT / local_path
    if local.exists():
        return str(local)
    return docker_path

APP_ENV = os.getenv("APP_ENV", "development").lower()
RUNNING_ON_VERCEL = bool(os.getenv("VERCEL"))
FRONTEND_DIST_DIR = _default_path("FRONTEND_DIST_DIR", "frontend/dist", "/app/frontend/dist")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)
REQUIRE_SUPABASE = APP_ENV == "production" or RUNNING_ON_VERCEL

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
TEMPLATES_DIR = _default_path("TEMPLATES_DIR", "templates", "/app/templates")
RECIPIENTS_DIR = os.getenv("RECIPIENTS_DIR", "/data/recipients")
UNSUBSCRIBED_FILE = os.getenv("UNSUBSCRIBED_FILE", "/data/recipients/unsubscribed.csv")
SUBSCRIBERS_FILE = os.getenv("SUBSCRIBERS_FILE", "/data/recipients/subscribers.csv")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
SEND_BATCH_SIZE = int(os.getenv("SEND_BATCH_SIZE", "100"))
