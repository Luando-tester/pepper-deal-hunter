import json
import logging
from pathlib import Path
from config import SEEN_DEALS_FILE, KNOWN_SOURCES_FILE, EVM_BASE_WALLET, SOLANA_WALLET
from sources import ALL_FETCHERS
from filter import is_clean_deal
from telegram import send_telegram_message, format_deals_message, format_new_source_prompt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("pepper-hunter")

# Danh sách nguồn mới đề xuất mở rộng (chỉ hỏi user 1 lần, không tự thêm vào cron)
CANDIDATE_NEW_SOURCES = [
    {
        "key": "goatmarket",
        "name": "GOAT Market (goatmarket.com)",
        "description": "Bảng tổng hợp bounty trả tiền thật cho AI agents & dev từ GitHub/Immunefi/AIcrowd",
    },
    {
        "key": "opire",
        "name": "Opire (opire.dev)",
        "description": "Nền tảng GitHub issue bounties nhận 100% thưởng USD khi PR được merge",
    },
]


def _load_json_set(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def _save_json_set(path: Path, items: set[str]) -> None:
    path.write_text(json.dumps(sorted(items), ensure_ascii=False, indent=2), encoding="utf-8")


def run_hunter() -> None:
    seen_deals = _load_json_set(SEEN_DEALS_FILE)
    asked_sources = _load_json_set(KNOWN_SOURCES_FILE)

    logger.info("Bắt đầu chu kỳ quét kèo | Ví Base mặc định: %s | Ví Solana: %s", EVM_BASE_WALLET, SOLANA_WALLET)

    fresh_clean_deals: list[dict] = []

    for source_name, fetcher in ALL_FETCHERS:
        raw_deals = fetcher()
        logger.info("[%s] Quét được %d mục thô.", source_name, len(raw_deals))

        for deal in raw_deals:
            deal_id = deal["id"]
            if deal_id in seen_deals:
                continue

            ok, reason = is_clean_deal(deal)
            # Đánh dấu đã xử lý để không quét lặp lại kèo cũ ở giờ sau
            seen_deals.add(deal_id)

            if ok:
                fresh_clean_deals.append(deal)
            else:
                logger.debug("Loại kèo %s: %s", deal_id, reason)

    # 1. Chỉ nhắn Telegram khi có ít nhất 1 kèo SẠCH MỚI (không spam nếu không có gì mới)
    if fresh_clean_deals:
        msg = format_deals_message(fresh_clean_deals)
        if send_telegram_message(msg):
            logger.info("Đã gửi %d kèo mới lên Telegram.", len(fresh_clean_deals))
    else:
        logger.info("Không có kèo sạch mới -> im lặng (không gửi Telegram).")

    # 2. Kiểm tra nguồn mới đáng mở rộng (hỏi 1 lần duy nhất, chờ user xác nhận, không tự thêm)
    for src in CANDIDATE_NEW_SOURCES:
        if src["key"] not in asked_sources:
            question = format_new_source_prompt(src["name"], src["description"])
            if send_telegram_message(question):
                asked_sources.add(src["key"])
                logger.info("Đã gửi đề xuất nguồn mới: %s", src["name"])

    _save_json_set(SEEN_DEALS_FILE, seen_deals)
    _save_json_set(KNOWN_SOURCES_FILE, asked_sources)


if __name__ == "__main__":
    run_hunter()