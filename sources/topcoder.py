import logging
import requests
from config import DEFAULT_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

# CẦN KIỂM TRA LẠI URL nếu Topcoder nâng cấp version API challenges (v5/v6)
TOPCODER_CHALLENGES_URL = "https://api.topcoder.com/v6/challenges"


def fetch_topcoder_deals() -> list[dict]:
    """
    Quét Topcoder v6 API challenges đang mở (không cần auth).
    """
    try:
        resp = requests.get(
            TOPCODER_CHALLENGES_URL,
            params={"status": "Active", "perPage": 25, "page": 1},
            headers=DEFAULT_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("[Topcoder] Lỗi gọi API %s (cần kiểm tra URL v5/v6 thực tế): %s", TOPCODER_CHALLENGES_URL, exc)
        return []

    items = payload if isinstance(payload, list) else payload.get("result") or payload.get("data") or []
    deals = []
    for item in items:
        cid = str(item.get("id") or "")
        if not cid:
            continue

        # Tính tổng giải thưởng từ prizeSets nếu có
        total_prize = 0.0
        for pset in item.get("prizeSets") or []:
            if str(pset.get("type") or "").lower() in ("placement", ""):
                for p in pset.get("prizes") or []:
                    total_prize += float(p.get("value") or 0)
        if total_prize <= 0:
            total_prize = float(item.get("totalPrize") or 0)

        deals.append({
            "id": f"topcoder:{cid}",
            "source": "Topcoder",
            "title": str(item.get("name") or cid)[:120],
            "description": str(item.get("description") or item.get("type") or ""),
            "budget": total_prize,
            "currency": "USD",
            "deadline": str(item.get("submissionEndDate") or item.get("endDate") or "N/A"),
            "url": f"https://www.topcoder.com/challenges/{cid}",
            "region": "global",
            "network": "base",
            "requires_login": False,
            "deposit_required": False,
        })
    return deals