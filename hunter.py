from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from config import (
    STATE_DIR,
    SEEN_DEALS_FILE,
    KNOWN_SOURCES_FILE,
    EVM_BASE_WALLET,
    SOLANA_WALLET,
    TELEGRAM_CHAT_ID,
)
from sources import ALL_FETCHERS
from filter import is_clean_deal
from telegram import (
    send_telegram_message,
    read_telegram_updates,
    sync_telegram_offset_to_latest,
    wait_for_user_reply,
    pin_telegram_message,
    unpin_telegram_message,
    format_deals_message,
    format_new_source_prompt,
    format_login_needed_message,
    format_anomaly_alert,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("pepper-hunter")

PENDING_DEALS_FILE = STATE_DIR / "pending_deals.json"
ALERTS_LOG_FILE = STATE_DIR / "sent_alerts.json"
PINNED_FILE = STATE_DIR / "pinned_messages.json"

DEFAULT_CHAT_ID = TELEGRAM_CHAT_ID or "-1003951530584"

# Từ khóa xác nhận hoàn thành từ Luân trên Telegram (không phân biệt hoa thường)
DONE_KEYWORDS = ("đã thực hiện xong", "xong", "done")

# Trạng thái kèo CÒN cần Luân làm (tin nhắn pin giữ nguyên khi còn trạng thái này)
NEEDS_USER_STATUSES = ("needs_user_login", "needs_user_decision")

# Link trực tiếp (đầy đủ, không rút gọn) tới trang đăng nhập/submit của các nền tảng
# (đã kiểm chứng 16/11: Superteam = superteam.fun, MoltJobs = moltjobs.io,
# HYRVE = hyrveai.com — KHÔNG phải earn.superteam.fun / moltjobs.com / hyrve.com)
PLATFORM_LOGIN_URLS = {
    "Superteam Earn": "https://superteam.fun/",
    "Topcoder": "https://accounts.topcoder.com/member",
    "make.fun": "https://make.fun/",
    "GitHub Bounties": "https://github.com/login",
    "MoltJobs": "https://moltjobs.io/",
    "HYRVE": "https://hyrveai.com/",
}

# Danh sách nguồn mới đề xuất mở rộng (chỉ hỏi user 1 lần, không tự thêm vào cron).
# GOAT Market + Opire đã hỏi 16/11 và Luân quyết định SKIP cả 2 (GOAT: cert hỏng +
# dữ liệu cũ 3 tuần; Opire: chỉ 3 kèo, không escrow) — giữ danh sách trống cho tới
# khi đợt quét rộng tiếp theo tìm được nguồn mới.
CANDIDATE_NEW_SOURCES: list[dict] = []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _load_pending_deals() -> dict[str, dict]:
    if not PENDING_DEALS_FILE.exists():
        return {}
    try:
        data = json.loads(PENDING_DEALS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("deals"), dict):
            return data["deals"]
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def _save_pending_deals(deals_map: dict[str, dict]) -> None:
    payload = {
        "updated_at": _now_iso(),
        "deals": deals_map,
    }
    PENDING_DEALS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_pinned() -> dict:
    if not PINNED_FILE.exists():
        return {"announcements": [], "login_pins": {}}
    try:
        data = json.loads(PINNED_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                "announcements": data.get("announcements") or [],
                "login_pins": data.get("login_pins") or {},
            }
    except Exception:
        pass
    return {"announcements": [], "login_pins": {}}


def _save_pinned(pinned: dict) -> None:
    PINNED_FILE.write_text(json.dumps(pinned, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_direct_login_or_submit_url(deal: dict) -> str:
    """
    Ưu tiên link trực tiếp của kèo nếu là URL đầy đủ https://, ngược lại lấy trang đăng nhập chính thức của nền tảng.
    """
    deal_url = str(deal.get("url") or "").strip()
    if deal_url.startswith("https://") or deal_url.startswith("http://"):
        return deal_url
    return PLATFORM_LOGIN_URLS.get(deal.get("source", ""), "https://superteam.fun/")


def _classify_deal_action(deal: dict) -> tuple[str, str, str | None]:
    """
    Phân loại kèo sạch thành trạng thái & hành động tiếp theo cho Muse/Luân.
    QUAN TRỌNG: Hunter KHÔNG tự bid, KHÔNG tự nộp bài, KHÔNG tự comment/PR — chỉ phân loại & ghi trạng thái.
    Trả về: (status, next_action, login_url_or_none)
    """
    source = str(deal.get("source") or "")
    title_desc = f"{deal.get('title', '')} {deal.get('description', '')}".lower()

    # 1. Synmerco: Watch cron 15 phút xử lý theo bid gate riêng, tuyệt đối không bid trùng tại đây
    if source == "Synmerco":
        return (
            "synmerco_watch_cron_handles",
            "Để watch cron 15 phút tự động đánh giá bid gate và đặt bid (không bid trùng).",
            None,
        )

    # 2. Superteam Earn hoặc kèo có dấu hiệu cần tài khoản đăng nhập Web/KYC/Submit form
    login_indicators = ("sign in", "log in", "connect wallet", "submit form", "kyc", "account required")
    if source == "Superteam Earn" or any(k in title_desc for k in login_indicators):
        direct_url = _resolve_direct_login_or_submit_url(deal)
        return (
            "needs_user_login",
            f"Chờ Luân đăng nhập/kết nối tài khoản tại {direct_url} và nhắn 'xong' trên Telegram.",
            direct_url,
        )

    # 3. make.fun / GitHub Bounties / Topcoder: Muse + Gemini tự thực thi và nộp qua CLI/PR
    if source in ("make.fun", "GitHub Bounties", "Topcoder"):
        return (
            "needs_muse_execution",
            "Muse + Gemini nghiên cứu/viết code và nộp bài qua CLI/PR/Submission portal.",
            None,
        )

    # 4. Các nguồn/kèo còn lại chưa rõ quy trình chuẩn -> đẩy sang quyết định của Luân
    return (
        "needs_user_decision",
        f"Nguồn '{source}' hoặc yêu cầu task chưa có playbook tự động — chờ Luân quyết định.",
        None,
    )


def _classify_and_record(
    deals: list[dict],
    pending_deals: dict[str, dict],
    pinned: dict,
    send_login_msg: bool,
) -> None:
    """Phân loại kèo sạch mới vào pending_deals.json (ghi trạng thái, không tự bid/nộp)."""
    for deal in deals:
        deal_id = deal["id"]
        status, next_action, login_url = _classify_deal_action(deal)

        existing = pending_deals.get(deal_id, {})
        notified_states = set(existing.get("notified_states", []))
        notified_states.add("new_deal_announced")

        record = {
            "id": deal_id,
            "source": deal["source"],
            "title": deal["title"],
            "budget": deal["budget"],
            "currency": deal.get("currency", "USD"),
            "deadline": deal.get("deadline", "N/A"),
            "url": deal["url"],
            "payout_network": deal.get("payout_network", "Base (EVM)"),
            "payout_wallet": deal.get("payout_wallet", EVM_BASE_WALLET),
            "mode": "auto_handle",
            "status": status,
            "next_action": next_action,
            "login_url": login_url,
            "pinned_message_id": existing.get("pinned_message_id"),
            "notified_states": sorted(notified_states),
            "created_at": existing.get("created_at") or _now_iso(),
            "updated_at": _now_iso(),
        }

        # Nếu trạng thái là needs_user_login và chưa gửi tin nhắc đăng nhập -> gửi 1 lần duy nhất + pin
        if send_login_msg and status == "needs_user_login" and "needs_user_login" not in notified_states:
            target_login_url = login_url or _resolve_direct_login_or_submit_url(deal)
            login_msg = format_login_needed_message(deal, target_login_url)
            sent = send_telegram_message(login_msg)
            if sent and sent.get("message_id"):
                mid = sent["message_id"]
                record["pinned_message_id"] = mid
                pinned["login_pins"][deal_id] = mid
                if pin_telegram_message(DEFAULT_CHAT_ID, mid):
                    logger.info("Đã gửi + pin yêu cầu đăng nhập cho kèo %s", deal_id)
                else:
                    logger.warning("Đã gửi yêu cầu đăng nhập cho kèo %s (pin thất bại — bot chưa là admin?)", deal_id)
                notified_states.add("needs_user_login")
                record["notified_states"] = sorted(notified_states)

        pending_deals[deal_id] = record
        logger.info("Phân loại kèo %s -> status=%s", deal_id, status)


def _process_user_done_messages(
    messages: list[dict], pending_deals: dict[str, dict], pinned: dict
) -> bool:
    """
    Kiểm tra tin nhắn Telegram mới: nếu chứa 'xong' / 'done' / 'đã thực hiện xong',
    chuyển các kèo đang ở trạng thái 'needs_user_login' sang 'user_done'
    và GỠ PIN tin nhắn đăng nhập của kèo đó.
    """
    if not messages:
        return False

    has_done_signal = False
    for msg in messages:
        text_lower = msg.get("text", "").lower()
        if any(kw in text_lower for kw in DONE_KEYWORDS):
            has_done_signal = True
            break

    if not has_done_signal:
        return False

    updated_any = False
    for deal_id, record in pending_deals.items():
        if record.get("status") == "needs_user_login":
            record["status"] = "user_done"
            record["next_action"] = "Luân đã xác nhận xong bước đăng nhập — Muse tiếp tục xử lý ở lượt sau."
            record["user_done_at"] = _now_iso()
            # Gỡ pin tin nhắn đăng nhập của kèo này (task đã xong)
            mid = record.get("pinned_message_id") or pinned["login_pins"].get(deal_id)
            if mid:
                unpin_telegram_message(DEFAULT_CHAT_ID, mid)
                pinned["login_pins"].pop(deal_id, None)
                record["pinned_message_id"] = None
            updated_any = True

    if updated_any:
        logger.info("Luân đã xong, tiếp tục xử lý")
    return updated_any


def _sweep_announcement_pins(pending_deals: dict[str, dict], pinned: dict) -> None:
    """
    Gỡ pin tin nhắn thông báo kèo khi KHÔNG còn kèo nào trong đó cần Luân làm
    (mọi kèo đã sang trạng thái không cần user: user_done / needs_muse_execution /
    synmerco_watch_cron_handles). Tin mới tới sẽ được pin mới.
    """
    kept = []
    for ann in pinned.get("announcements", []):
        deal_ids = ann.get("deal_ids") or []
        mid = ann.get("message_id")
        still_needs_user = False
        for did in deal_ids:
            rec = pending_deals.get(did)
            if rec is None:
                continue  # kèo chưa phân loại (user đã trả lời trong 2 phút) -> coi như còn chờ
            if rec.get("status") in NEEDS_USER_STATUSES:
                still_needs_user = True
                break
        if still_needs_user:
            kept.append(ann)
        elif mid:
            unpin_telegram_message(DEFAULT_CHAT_ID, mid)
    pinned["announcements"] = kept


def _send_alert_once(alert_key: str, title: str, detail: str, sent_alerts: set[str]) -> None:
    """
    Gửi cảnh báo phát sinh lạ qua Telegram tối đa 1 lần cho mỗi alert_key (chống spam).
    """
    if alert_key in sent_alerts:
        return
    if send_telegram_message(format_anomaly_alert(title, detail)):
        sent_alerts.add(alert_key)


def run_hunter() -> None:
    seen_deals = _load_json_set(SEEN_DEALS_FILE)
    asked_sources = _load_json_set(KNOWN_SOURCES_FILE)
    sent_alerts = _load_json_set(ALERTS_LOG_FILE)
    pending_deals = _load_pending_deals()
    pinned = _load_pinned()

    logger.info(
        "Bắt đầu chu kỳ quét kèo | Ví Base mặc định: %s | Ví Solana: %s",
        EVM_BASE_WALLET,
        SOLANA_WALLET,
    )

    # Bước 0: Đọc tin nhắn Telegram mới trước khi quét (nghe lệnh 'xong' / 'done' / 'đã thực hiện xong')
    incoming_messages = read_telegram_updates(advance_offset=True)
    if _process_user_done_messages(incoming_messages, pending_deals, pinned):
        _save_pending_deals(pending_deals)
        _save_pinned(pinned)

    fresh_clean_deals: list[dict] = []

    # Bước 1: Quét 7 nguồn và lọc qua Cổng Sạch
    for source_name, fetcher in ALL_FETCHERS:
        try:
            raw_deals = fetcher()
        except Exception as exc:
            logger.error("[%s] Lỗi không mong muốn khi quét: %s", source_name, exc)
            _send_alert_once(
                f"source_crash:{source_name}",
                f"Lỗi nguồn {source_name}",
                f"Fetcher gặp ngoại lệ lạ: {str(exc)[:180]}",
                sent_alerts,
            )
            continue

        if not isinstance(raw_deals, list):
            _send_alert_once(
                f"bad_format:{source_name}",
                f"API đổi format tại {source_name}",
                "Dữ liệu trả về không phải danh sách chuẩn, cần kiểm tra lại parser.",
                sent_alerts,
            )
            continue

        logger.info("[%s] Quét được %d mục thô.", source_name, len(raw_deals))

        for deal in raw_deals:
            deal_id = deal.get("id")
            if not deal_id or deal_id in seen_deals:
                continue

            ok, reason = is_clean_deal(deal)
            seen_deals.add(deal_id)

            if ok:
                fresh_clean_deals.append(deal)
            else:
                logger.debug("Loại kèo %s: %s", deal_id, reason)
                # Nếu phát hiện dấu hiệu lừa đảo / đặt cọc / gửi crypto trước thì hú 1 lần
                if "cọc" in reason or "send crypto" in reason or "kyc fee" in reason:
                    _send_alert_once(
                        f"scam_deal:{deal_id}",
                        f"Nghi vấn lừa đảo trên {source_name}",
                        f"Kèo '{deal.get('title', deal_id)[:80]}' bị chặn vì: {reason}",
                        sent_alerts,
                    )

    # Bước 2: Nếu có kèo sạch MỚI -> gửi Telegram, chờ 120s kiểm tra phản hồi, nếu im lặng thì tự phân loại
    if fresh_clean_deals:
        # Đồng bộ offset trước khi gửi để chỉ bắt tin nhắn trả lời SAU thời điểm bot gửi danh sách kèo
        sync_telegram_offset_to_latest()
        msg = format_deals_message(fresh_clean_deals)
        sent = send_telegram_message(msg)

        if sent:
            logger.info("Đã gửi %d kèo mới lên Telegram. Bắt đầu chờ 120 giây...", len(fresh_clean_deals))
            # Pin tin nhắn thông báo kèo (task cần Luân xem) — thất bại thì thôi, tin vẫn còn đó
            if sent.get("message_id"):
                mid = sent["message_id"]
                if pin_telegram_message(DEFAULT_CHAT_ID, mid):
                    pinned["announcements"].append({
                        "message_id": mid,
                        "deal_ids": [d["id"] for d in fresh_clean_deals],
                    })
                    _save_pinned(pinned)
                else:
                    logger.warning("Pin tin nhắn kèo thất bại — bot có thể chưa là admin nhóm.")

            replies = wait_for_user_reply(wait_seconds=120, poll_interval=10)

            # Kiểm tra nếu trong lúc chờ 2 phút Luân nhắn "xong"/"done" cho kèo cũ thì vẫn cập nhật
            _process_user_done_messages(replies, pending_deals, pinned)

            if replies:
                logger.info("user replied, waiting")
                # Luân đã trả lời -> vẫn phân loại kèo để theo dõi pin, nhưng KHÔNG gửi tin đăng nhập vội
                # (Luân đang nói chuyện, Muse chính sẽ đưa link trong chat)
                _classify_and_record(fresh_clean_deals, pending_deals, pinned, send_login_msg=False)
            else:
                # Không ai trả lời sau 120s -> tự phân loại & ghi trạng thái vào state/pending_deals.json
                # LƯU Ý: Không tự bid, không tự nộp bài, không tự comment/PR.
                _classify_and_record(fresh_clean_deals, pending_deals, pinned, send_login_msg=True)
        else:
            logger.warning("Không gửi được tin nhắn Telegram (kiểm tra token/chat_id), bỏ qua bước chờ 120s.")
    else:
        logger.info("Không có kèo sạch mới -> im lặng (không gửi Telegram).")

    # Bước 3: Kiểm tra nguồn mới đáng mở rộng (hỏi 1 lần duy nhất, chờ user xác nhận, không tự thêm)
    for src in CANDIDATE_NEW_SOURCES:
        if src["key"] not in asked_sources:
            question = format_new_source_prompt(src["name"], src["description"])
            if send_telegram_message(question):
                asked_sources.add(src["key"])
                logger.info("Đã gửi đề xuất nguồn mới: %s", src["name"])

    # Bước 4: Gỡ pin các tin nhắn thông báo kèo mà không còn kèo nào cần Luân làm
    _sweep_announcement_pins(pending_deals, pinned)

    _save_json_set(SEEN_DEALS_FILE, seen_deals)
    _save_json_set(KNOWN_SOURCES_FILE, asked_sources)
    _save_json_set(ALERTS_LOG_FILE, sent_alerts)
    _save_pending_deals(pending_deals)
    _save_pinned(pinned)


if __name__ == "__main__":
    run_hunter()
