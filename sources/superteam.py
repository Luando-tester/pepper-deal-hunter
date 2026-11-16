import logging
import requests
from config import DEFAULT_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

# Endpoint thật (đã đối chiếu connector custom.superteam): https://superteam.fun/api/listings?status=open&take=50
SUPERTEAM_LISTINGS_URL = "https://superteam.fun/api/listings"


def fetch_superteam_deals() -> list[dict]:
    """
    Quét Superteam Earn public listings (không cần API key).
    Mạng chỉ hỗ trợ Solana -> filter.py sẽ tự gắn ví Solana EMCzkUmfVLcbey2eugzppupQkz4Z8FiosLpMP9opUDv1.
    """
    try:
        resp = requests.get(
            SUPERTEAM_LISTINGS_URL,
            params={"status": "open", "take": 30},
            headers=DEFAULT_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("[Superteam Earn] Lỗi gọi API %s (cần kiểm tra URL thực tế): %s", SUPERTEAM_LISTINGS_URL, exc)
        return []

    items = payload if isinstance(payload, list) else payload.get("listings") or payload.get("data") or []
    deals = []
    for item in items:
        slug = str(item.get("slug") or item.get("id") or "")
        if not slug:
            continue
        # Ưu tiên usdValue (giá trị USD thật) trước rewardAmount (có thể là số lượng token thô,
        # vd 689655 BAOBAO — không phải USD). Fallback sang budget nếu thiếu cả hai.
        reward = float(item.get("usdValue") or item.get("rewardAmount") or item.get("budget") or 0)
        region = str(item.get("region") or "GLOBAL")
        deals.append({
            "id": f"superteam:{slug}",
            "source": "Superteam Earn",
            "title": str(item.get("title") or slug)[:120],
            "description": str(item.get("description") or item.get("skills") or ""),
            "budget": reward,
            "currency": str(item.get("token") or "USDC"),
            "deadline": str(item.get("deadline") or "N/A"),
            "url": f"https://superteam.fun/earn/listing/{slug}",
            "region": region,
            "network": "solana_only",
            "requires_login": False,
            "deposit_required": False,
        })
    return deals