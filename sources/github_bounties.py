import logging
import re
import requests
from config import DEFAULT_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

GITHUB_SEARCH_ISSUES_URL = "https://api.github.com/search/issues"


def _extract_usd_amount(text: str) -> float:
    """Trích xuất số tiền USD rõ ràng từ tiêu đề/nhãn issue (ví dụ: $100, $250, 500 USDC)."""
    matches = re.findall(r"(?:\$|USD\s*|USDC\s*)(\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)
    if not matches:
        return 0.0
    amounts = [float(m) for m in matches]
    return max(amounts)


def fetch_github_bounties() -> list[dict]:
    """
    Quét GitHub public issues có gắn label bounty (Algora / Opire / bounty) qua GitHub Search API public.
    """
    query = 'is:issue is:open label:bounty "$" in:title'
    try:
        resp = requests.get(
            GITHUB_SEARCH_ISSUES_URL,
            params={"q": query, "sort": "created", "order": "desc", "per_page": 25},
            headers={**DEFAULT_HEADERS, "Accept": "application/vnd.github+json"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("[GitHub Bounties] Lỗi gọi GitHub Search API: %s", exc)
        return []

    deals = []
    for item in payload.get("items", []):
        if item.get("pull_request"):
            continue
        title = str(item.get("title") or "")
        labels_text = " ".join(lbl.get("name", "") for lbl in item.get("labels", []))
        budget = _extract_usd_amount(f"{title} {labels_text}")
        if budget <= 0:
            continue

        issue_id = str(item.get("id"))
        deals.append({
            "id": f"github:{issue_id}",
            "source": "GitHub Bounties",
            "title": title[:120],
            "description": str(item.get("body") or "")[:500],
            "budget": budget,
            "currency": "USD",
            "deadline": "First valid PR",
            "url": str(item.get("html_url") or ""),
            "region": "global",
            "network": "base",
            "requires_login": False,
            "deposit_required": False,
        })
    return deals