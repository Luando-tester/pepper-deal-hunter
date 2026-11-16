import logging
import requests
from config import SYNMERCO_BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT
from credentials import synmerco_auth_headers

logger = logging.getLogger(__name__)


def fetch_synmerco_deals() -> list[dict]:
    """
    Quét Synmerco intents đang mở: GET /v1/intents?status=open
    Auth qua surrogate custom.synmerco (Secure Vault) hoặc SYNMERCO_API_KEY.
    """
    auth = synmerco_auth_headers()
    if not auth:
        logger.info("[Synmerco] Bỏ qua vì chưa có credential.")
        return []

    url = f"{SYNMERCO_BASE_URL}/v1/intents"
    headers = {**DEFAULT_HEADERS, **auth}

    try:
        resp = requests.get(url, params={"status": "open"}, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("[Synmerco] Lỗi gọi API %s: %s", url, exc)
        return []

    items = payload if isinstance(payload, list) else payload.get("intents") or payload.get("data") or []
    deals = []
    for item in items:
        intent_id = str(item.get("id") or item.get("intent_id") or "")
        if not intent_id:
            continue
        budget = 0.0
        # Synmerco trả budgetCents dạng STRING (vd "900") — phải chia 100 ra USD.
        # Fallback sang các tên trường khác nếu API đổi.
        raw_cents = item.get("budgetCents")
        if raw_cents is not None:
            try:
                budget = float(raw_cents) / 100.0
            except (TypeError, ValueError):
                budget = 0.0
        if budget <= 0:
            budget = float(item.get("budget") or item.get("amount") or item.get("reward") or 0)
        funded = item.get("funded")
        # Nếu API có cờ funded rõ ràng mà False thì bỏ qua ngay
        if funded is False:
            continue

        deals.append({
            "id": f"synmerco:{intent_id}",
            "source": "Synmerco",
            "title": str(item.get("title") or item.get("description") or f"Intent #{intent_id}")[:120],
            "description": str(item.get("description") or ""),
            "budget": budget,
            "currency": str(item.get("currency") or "USDC"),
            "deadline": str(item.get("deadline") or item.get("expires_at") or "N/A"),
            "url": str(item.get("url") or f"{SYNMERCO_BASE_URL}/intents/{intent_id}"),
            "region": str(item.get("region") or "global"),
            "network": str(item.get("network") or "base"),
            "requires_login": False,
            "deposit_required": bool(item.get("deposit_required", False)),
        })
    return deals