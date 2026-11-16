import logging
import requests
from config import MAKEFUN_BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT
from credentials import makefun_auth_headers

logger = logging.getLogger(__name__)


def fetch_makefun_deals() -> list[dict]:
    """
    Quét make.fun competitions/bounties: GET /api/competitions
    (x-api-key qua surrogate custom.makefun hoặc MAKEFUN_API_KEY).
    Mạng Solana -> tự động map sang ví Solana của Luân.
    """
    url = f"{MAKEFUN_BASE_URL}/api/competitions"
    headers = {**DEFAULT_HEADERS, **makefun_auth_headers()}

    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("[make.fun] Lỗi gọi API %s: %s", url, exc)
        return []

    items = payload if isinstance(payload, list) else payload.get("competitions") or payload.get("data") or []
    deals = []
    for item in items:
        status = str(item.get("status") or "open").lower()
        if status not in ("open", "active"):
            continue
        comp_id = str(item.get("id") or item.get("slug") or "")
        if not comp_id:
            continue
        prize = float(item.get("prize") or item.get("pool") or item.get("budget") or 0)
        deals.append({
            "id": f"makefun:{comp_id}",
            "source": "make.fun",
            "title": str(item.get("title") or item.get("name") or comp_id)[:120],
            "description": str(item.get("description") or ""),
            "budget": prize,
            "currency": "USDC",
            "deadline": str(item.get("deadline") or item.get("ends_at") or "N/A"),
            "url": str(item.get("url") or f"{MAKEFUN_BASE_URL}/competitions/{comp_id}"),
            "region": "global",
            "network": "solana_only",
            "requires_login": False,
            "deposit_required": False,
        })
    return deals