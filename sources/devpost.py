import logging
import re
import requests
from config import DEFAULT_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

# API public chính thức của Devpost (không cần auth)
DEVPOST_HACKATHONS_URL = "https://devpost.com/api/hackathons"


def _parse_prize_text(prize_raw: str) -> float:
    """
    Trích xuất số tiền từ chuỗi HTML/text của Devpost (ví dụ: '$<span data-currency-value>35,000</span>').
    Chỉ lấy giải USD ($) để đảm bảo quy đổi chuẩn.
    """
    if not prize_raw:
        return 0.0
    clean = re.sub(r"<[^>]+>", "", str(prize_raw)).replace(",", "").strip()
    if "$" not in clean and "USD" not in clean.upper():
        return 0.0
    match = re.search(r"(\d+(?:\.\d+)?)", clean)
    if not match:
        return 0.0
    try:
        return float(match.group(1))
    except ValueError:
        return 0.0


def fetch_devpost_deals() -> list[dict]:
    """
    Quét các hackathon đang mở trên Devpost có giải thưởng tiền mặt USD > 0 (online / global).
    """
    try:
        resp = requests.get(
            DEVPOST_HACKATHONS_URL,
            params={
                "open_state[]": "open",
                "challenge_type[]": "online",
                "order_by": "deadline",
                "page": 1,
            },
            headers=DEFAULT_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("[Devpost] Lỗi gọi API %s: %s", DEVPOST_HACKATHONS_URL, exc)
        return []

    items = payload.get("hackathons") if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return []

    deals = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("open_state") or "").lower() != "open":
            continue

        hid = str(item.get("id") or "")
        if not hid:
            continue

        budget = _parse_prize_text(str(item.get("prize_amount") or ""))
        if budget <= 0:
            continue

        # Bỏ qua hackathon chỉ dành cho học sinh phổ thông/sinh viên nếu ghi rõ hoặc giới hạn vùng
        themes = [t.get("name", "") for t in (item.get("themes") or []) if isinstance(t, dict)]
        eligibility = str(item.get("eligibility_requirement_invite_only") or "")
        if eligibility.lower() == "true":
            continue

        url = str(item.get("url") or "").strip()
        if not url.startswith("http"):
            continue

        deals.append({
            "id": f"devpost:{hid}",
            "source": "Devpost",
            "title": str(item.get("title") or f"Devpost #{hid}")[:120],
            "description": f"Themes: {', '.join(themes)} | {item.get('organization_name', '')}"[:500],
            "budget": budget,
            "currency": "USD",
            "deadline": str(item.get("submission_period_dates") or "N/A"),
            "url": url,
            "region": "global",
            "network": "base",
            "requires_login": False,
            "deposit_required": False,
        })

    return deals