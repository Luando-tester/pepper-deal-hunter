import logging
import requests
from config import HYRVE_BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT
from credentials import hyrve_auth_headers

logger = logging.getLogger(__name__)


def fetch_hyrve_deals() -> list[dict]:
    """
    Quét HYRVE: GET /v1/jobs (X-API-Key qua surrogate custom.hyrve hoặc HYRVE_API_KEY).
    Host thật: https://api.hyrveai.com.
    """
    auth = hyrve_auth_headers()
    if not auth:
        logger.info("[HYRVE] Bỏ qua vì chưa có credential.")
        return []

    url = f"{HYRVE_BASE_URL}/v1/jobs"
    headers = {**DEFAULT_HEADERS, **auth}

    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("[HYRVE] Lỗi gọi API %s (kiểm tra HYRVE_BASE_URL): %s", url, exc)
        return []

    items = payload if isinstance(payload, list) else payload.get("jobs") or payload.get("data") or []
    deals = []
    for item in items:
        status = str(item.get("status") or "OPEN").upper()
        if status not in ("OPEN", "ACTIVE"):
            continue
        job_id = str(item.get("id") or "")
        if not job_id:
            continue
        budget = float(item.get("budget") or item.get("reward") or 0)
        deals.append({
            "id": f"hyrve:{job_id}",
            "source": "HYRVE",
            "title": str(item.get("title") or f"HYRVE #{job_id}")[:120],
            "description": str(item.get("description") or ""),
            "budget": budget,
            "currency": str(item.get("currency") or "USD"),
            "deadline": str(item.get("deadline") or "N/A"),
            "url": str(item.get("url") or f"{HYRVE_BASE_URL}/jobs/{job_id}"),
            "region": str(item.get("region") or "global"),
            "network": str(item.get("network") or "base"),
            "requires_login": False,
            "deposit_required": bool(item.get("deposit_required", False)),
        })
    return deals