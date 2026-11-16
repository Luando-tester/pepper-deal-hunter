import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)

SEEN_DEALS_FILE = STATE_DIR / "seen_deals.json"
KNOWN_SOURCES_FILE = STATE_DIR / "known_sources.json"

# Ví nhận thưởng chuẩn của PepperResearch
EVM_BASE_WALLET = "0xd170ad7a09EC585Fcb37DC7a9C37d65b63783B61"
SOLANA_WALLET = "EMCzkUmfVLcbey2eugzppupQkz4Z8FiosLpMP9opUDv1"

# Telegram Bot API
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# API Keys của các nguồn (đọc hoàn toàn từ biến môi trường)
SYNMERCO_API_KEY = os.getenv("SYNMERCO_API_KEY", "").strip()
SYNMERCO_BASE_URL = os.getenv("SYNMERCO_BASE_URL", "https://synmerco-escrow.onrender.com").rstrip("/")

MOLTJOBS_API_KEY = os.getenv("MOLTJOBS_API_KEY", "").strip()
MOLTJOBS_BASE_URL = os.getenv("MOLTJOBS_BASE_URL", "https://api.moltjobs.io").rstrip("/")

HYRVE_API_KEY = os.getenv("HYRVE_API_KEY", "").strip()
HYRVE_BASE_URL = os.getenv("HYRVE_BASE_URL", "https://api.hyrveai.com").rstrip("/")

MAKEFUN_API_KEY = os.getenv("MAKEFUN_API_KEY", "").strip()
MAKEFUN_BASE_URL = os.getenv("MAKEFUN_BASE_URL", "https://make.fun").rstrip("/")

# HTTP Timeout mặc định (giây)
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))

DEFAULT_HEADERS = {
    "User-Agent": "PepperResearch-DealHunter/1.0",
    "Accept": "application/json",
}