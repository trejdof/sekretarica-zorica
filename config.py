import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ALLOWED_USER_ID = int(os.environ["ALLOWED_USER_ID"])
GALLERY_URL = os.environ.get("GALLERY_URL", "http://localhost:8090")
GALLERY_SECRET = os.environ["GALLERY_SECRET"]
MEDIA_DIR = os.environ.get("MEDIA_DIR", os.path.join(os.path.dirname(__file__), "media"))
