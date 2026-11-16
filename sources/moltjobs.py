import logging
import requests
from config import MOLTJOBS_BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT
from credentials import moltjobs_auth_headers

logger = logging.getLogger(__name__)


def fetch_moltjobs_deals() -> list[dict]:
    """
    Quét MoltJobs: GET /v1/jobs?status=OPEN (Bearer qua surrogate custom.moltjobs
    hoặc MOLTJOBS_API_KEY). Host thật: https://api.moltjobs.io.
    """
    auth = moltjobs_auth_headers()
    if not auth:
        logger.info("[MoltJobs] Bỏ qua vì chưa có credential.")
        return []

    url = f"{MOLTJOBS_BASE_URL}/v1/jobs"
    headers = {**DEFAULT_HEADERS, **auth}

    try:
        resp = requests.get(url, params={"status": "OPEN"}, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("[MoltJobs] Lỗi gọi API %s (kiểm tra MOLTJOBS_BASE_URL): %s", url, exc)
        return []

    items = payload if isinstance(payload, list) else payload.get("jobs") or payload.get("data") or []
    deals = []
    for item in items:
        job_id = str(item.get("id") or item.get("job_id") or "")
        if not job_id:
            continue
        # Chỉ lấy kèo đã nạp tiền escrow nếu có trường funded
        if item.get("funded") is False:
            continue
        budget = float(item.get("budget") or item.get("reward") or item.get("payout") or 0)
        deals.append({
            "id": f"moltjobs:{job_id}",
            "source": "MoltJobs",
            "title": str(item.get("title") or f"Job #{job_id}")[:120],
            "description": str(item.get("description") or ""),
            "budget": budget,
            "currency": str(item.get("currency") or "USDC"),
            "deadline": str(item.get("deadline") or item.get("expires_at") or "N/A"),
            "url": str(item.get("url") or f"{MOLTJOBS_BASE_URL}/jobs/{job_id}"),
            "region": str(item.get("region") or "global"),
            "network": str(item.get("network") or "base"),
            "requires_login": False,
            "deposit_required": bool(item.get("deposit_required", False)),
        })
    return deals