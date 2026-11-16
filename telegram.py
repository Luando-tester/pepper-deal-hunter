"""Telegram I/O cho PepperResearch Deal Hunter.

Gửi tin + đọc tin nhắn + pin/unpin qua Telegram Bot API.

QUAN TRỌNG (đã kiểm chứng 12–16/11): urllib/requests TRỰC TIẾP tới
api.telegram.org bị lớp egress của VM cắt kết nối. Mọi gọi API phải đi qua
curl với surrogate RAW trong URL (cơ chế của helper
~/workspace/custom-connectors/custom.telegram/bin/telegram.py).
Module này tự replicate cơ chế đó (không gọi helper qua subprocess cho
getUpdates/pin — helper chỉ có lệnh send). Khi chạy standalone ngoài VM
(không có surrogate), fallback sang requests với TELEGRAM_BOT_TOKEN.

send_telegram_message trả về dict kết quả (gồm message_id) để hunter pin
được tin nhắn; trả None khi gửi lỗi.
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, REQUEST_TIMEOUT, STATE_DIR

logger = logging.getLogger(__name__)

TELEGRAM_OFFSET_FILE = STATE_DIR / "telegram_offset.json"
TELEGRAM_HELPER = os.path.expanduser(
    "~/workspace/custom-connectors/custom.telegram/bin/telegram.py"
)
DEFAULT_CHAT_ID = "-5518467945"  # Nhóm PepperResearch — Kiếm tiền

_SURROGATE_RE = re.compile(r"^hsurr:[A-Za-z0-9_-]+$")

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
try:
    from dynamic_credentials import dynamic_credential_entry
except Exception:  # pragma: no cover - không có authd socket ở máy ngoài
    dynamic_credential_entry = None


# ---------------------------------------------------------------- offset
def _load_offset() -> int | None:
    if not TELEGRAM_OFFSET_FILE.exists():
        return None
    try:
        data = json.loads(TELEGRAM_OFFSET_FILE.read_text(encoding="utf-8"))
        val = data.get("last_update_id")
        return int(val) if val is not None else None
    except Exception:
        return None


def _save_offset(last_update_id: int) -> None:
    TELEGRAM_OFFSET_FILE.write_text(
        json.dumps({"last_update_id": last_update_id}, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------- send
def _send_via_helper(text: str) -> dict | None:
    """Gửi qua helper curl. Trả None nếu helper không chạy được (để fallback)."""
    chat_id = TELEGRAM_CHAT_ID or DEFAULT_CHAT_ID
    if not os.path.exists(TELEGRAM_HELPER):
        return None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(text)
            tmp_path = tmp.name
        try:
            proc = subprocess.run(
                ["python3", TELEGRAM_HELPER, "send", chat_id, "--text-file", tmp_path],
                capture_output=True,
                text=True,
                timeout=REQUEST_TIMEOUT + 15,
            )
        finally:
            os.unlink(tmp_path)
        if proc.returncode == 0:
            m = re.search(r"message_id=(\d+)", proc.stdout or "")
            return {"message_id": int(m.group(1))} if m else {"message_id": None}
        logger.warning(
            "[Telegram] Helper trả lỗi (rc=%s): %s", proc.returncode, proc.stderr[:200]
        )
        return None
    except Exception as exc:
        logger.warning("[Telegram] Không chạy được helper: %s", exc)
        return None


def _send_via_requests(text: str) -> dict | None:
    """Fallback trực tiếp qua Bot API (cần TELEGRAM_BOT_TOKEN trong env)."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning(
            "[Telegram] Chưa cấu hình TELEGRAM_BOT_TOKEN. Nội dung:\n%s", text
        )
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID or DEFAULT_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            return data.get("result") or {}
        logger.error("[Telegram] API trả về ok=false: %s", data)
        return None
    except Exception as exc:
        logger.error("[Telegram] Gửi tin nhắn thất bại: %s", exc)
        return None


def send_telegram_message(text: str) -> dict | None:
    """
    Gửi tin nhắn qua Telegram Bot API. Trả về dict kết quả (gồm message_id)
    nếu gửi thành công, hoặc None nếu lỗi. Không ném exception làm sập cron.
    """
    via_helper = _send_via_helper(text)
    if via_helper is not None:
        return via_helper
    return _send_via_requests(text)


# ------------------------------------------------------- Bot API (curl)
def _bot_api_via_curl(method: str, payload: dict | None = None) -> dict | None:
    """Gọi Bot API qua curl + surrogate RAW (đường duy nhất sống trên VM)."""
    if dynamic_credential_entry is None:
        return None
    try:
        entry = dynamic_credential_entry("custom.telegram", "access_token")
        placement = entry.get("placement")
        if not (isinstance(placement, dict) and "url_path_segment" in placement):
            return None
        surrogate = str(entry.get("surrogate", "")).strip()
        if not _SURROGATE_RE.match(surrogate):
            return None
    except Exception as exc:
        logger.debug("[Telegram] Không lấy được surrogate: %s", exc)
        return None

    url = "https://api.telegram.org/bot%s/%s" % (surrogate, method)
    config = 'url = "%s"\nmax-time = 30\nsilent\n' % url
    tmp = None
    try:
        cmd = ["curl", "-sS", "-K", "-"]
        if payload is not None:
            fd, tmp = tempfile.mkstemp(prefix="tg_body_", dir="/tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(payload))
            cmd = ["curl", "-sS", "-K", "-", "-X", "POST",
                   "-H", "Content-Type: application/json",
                   "--data-binary", "@" + tmp]
        out = subprocess.run(cmd, input=config, capture_output=True, text=True, timeout=40)
        if out.returncode != 0:
            logger.warning("[Telegram] curl %s rc=%s: %s", method, out.returncode, out.stderr[:200])
            return None
        data = json.loads(out.stdout)
        if data.get("ok"):
            return data.get("result")
        logger.warning("[Telegram] %s trả ok=false: %s", method, data)
        return None
    except Exception as exc:
        logger.warning("[Telegram] Lỗi gọi %s qua curl: %s", method, exc)
        return None
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _bot_api_via_requests(method: str, payload: dict | None = None) -> dict | None:
    """Fallback trực tiếp (cần TELEGRAM_BOT_TOKEN trong env)."""
    if not TELEGRAM_BOT_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        if payload is not None:
            resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        else:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data.get("result") if data.get("ok") else None
    except Exception as exc:
        logger.warning("[Telegram] Lỗi gọi %s qua requests: %s", method, exc)
        return None


def _bot_api(method: str, payload: dict | None = None) -> dict | None:
    """Gọi Bot API: curl+surrogate trước, requests sau (standalone)."""
    result = _bot_api_via_curl(method, payload)
    if result is not None:
        return result
    return _bot_api_via_requests(method, payload)


# ------------------------------------------------------- đọc tin nhắn
def read_telegram_updates(advance_offset: bool = True) -> list[dict]:
    """
    Đọc các tin nhắn mới trong nhóm bằng getUpdates.
    Chỉ đọc update_id lớn hơn offset đã lưu trong state/telegram_offset.json.
    """
    last_id = _load_offset()
    params: dict = {"timeout": 0}
    if last_id is not None:
        params["offset"] = last_id + 1

    result = _bot_api("getUpdates", params)
    if result is None:
        return []

    updates = result if isinstance(result, list) else []
    messages: list[dict] = []
    max_update_id = last_id

    for upd in updates:
        uid = upd.get("update_id")
        if isinstance(uid, int) and (max_update_id is None or uid > max_update_id):
            max_update_id = uid

        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            continue

        # Bỏ qua tin nhắn do chính bot gửi ra
        sender = msg.get("from") or {}
        if sender.get("is_bot"):
            continue

        # Nếu có cấu hình TELEGRAM_CHAT_ID thì chỉ lọc tin nhắn thuộc đúng nhóm/chat đó
        chat_id = str((msg.get("chat") or {}).get("id", ""))
        if TELEGRAM_CHAT_ID and chat_id != str(TELEGRAM_CHAT_ID):
            continue

        text = str(msg.get("text") or msg.get("caption") or "").strip()
        if not text:
            continue

        messages.append({
            "update_id": uid,
            "message_id": msg.get("message_id"),
            "date": msg.get("date", 0),
            "user_id": sender.get("id"),
            "username": sender.get("username") or sender.get("first_name") or "user",
            "text": text,
        })

    if advance_offset and max_update_id is not None and max_update_id != last_id:
        _save_offset(max_update_id)

    return messages


def sync_telegram_offset_to_latest() -> None:
    """
    Đồng bộ offset hiện tại trước khi gửi tin nhắn mới để tránh nhận nhầm tin cũ trước đó.
    """
    read_telegram_updates(advance_offset=True)


def wait_for_user_reply(wait_seconds: int = 120, poll_interval: int = 10) -> list[dict]:
    """
    Chờ tối đa `wait_seconds` (mặc định 120 giây) sau khi gửi danh sách kèo lên Telegram.
    Kiểm tra getUpdates định kỳ; nếu người dùng trả lời bất kỳ nội dung gì thì trả về ngay danh sách tin nhắn.
    """
    logger.info("[Telegram] Chờ phản hồi của Luân trong %d giây...", wait_seconds)
    deadline = time.monotonic() + wait_seconds

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        sleep_time = min(poll_interval, max(1.0, remaining))
        time.sleep(sleep_time)

        replies = read_telegram_updates(advance_offset=True)
        if replies:
            return replies

    return []


# ------------------------------------------------------- pin / unpin
def pin_telegram_message(chat_id: str, message_id: int) -> bool:
    """
    Ghim tin nhắn lên đầu nhóm (pinChatMessage).
    Cần bot là admin nhóm + quyền Pin Messages — nếu chưa có quyền, API trả lỗi
    và hàm trả False (không ném exception). Tin nhắn đã gửi vẫn còn đó.
    """
    result = _bot_api("pinChatMessage", {
        "chat_id": chat_id,
        "message_id": message_id,
        "disable_notification": True,
    })
    if result is not None:
        logger.info("[Telegram] Đã pin message_id=%s", message_id)
        return True
    logger.warning(
        "[Telegram] Pin message_id=%s thất bại (bot có thể chưa là admin nhóm "
        "hoặc chưa có quyền Pin Messages).", message_id
    )
    return False


def unpin_telegram_message(chat_id: str, message_id: int) -> bool:
    """Gỡ ghim 1 tin nhắn (unpinChatMessage). Trả False nếu lỗi, không ném exception."""
    result = _bot_api("unpinChatMessage", {
        "chat_id": chat_id,
        "message_id": message_id,
    })
    if result is not None:
        logger.info("[Telegram] Đã gỡ pin message_id=%s", message_id)
        return True
    logger.warning("[Telegram] Gỡ pin message_id=%s thất bại.", message_id)
    return False


# ------------------------------------------------------- format tin nhắn
def format_deals_message(new_deals: list[dict]) -> str:
    """
    Format ngắn gọn, tiếng Việt, mỗi kèo 1 dòng:
    [Nguồn] Tên kèo — $budget — deadline — link
    """
    lines = ["🎯 KÈO SẠCH MỚI (PepperResearch):"]
    for d in new_deals:
        budget_str = f"${d['budget']:g}"
        title = d["title"].replace("\n", " ").strip()
        lines.append(f"[{d['source']}] {title} — {budget_str} — {d['deadline']} — {d['url']}")
    lines.append("\n(Chờ 2 phút — nếu không ai phản hồi, hệ thống sẽ tự phân loại kèo.)")
    return "\n".join(lines)


def format_new_source_prompt(source_name: str, description: str) -> str:
    """
    Câu hỏi chuẩn khi phát hiện nguồn kèo mới chưa có trong danh sách quét (chờ user duyệt).
    """
    return f"Phát hiện nguồn kèo mới: {source_name} — {description}. Có thêm vào danh sách quét không?"


def format_login_needed_message(deal: dict, login_url: str) -> str:
    """
    Tin nhắn yêu cầu Luân đăng nhập / submit với link đầy đủ (không rút gọn).
    """
    title = deal["title"].replace("\n", " ").strip()
    budget_str = f"${deal['budget']:g}"
    return (
        f"🔐 CẦN ĐĂNG NHẬP ({deal['source']}): {title} ({budget_str})\n"
        f"Link trực tiếp: {login_url}\n"
        f"Bro đăng nhập/làm bước này giúp tui nhé."
    )


def format_anomaly_alert(alert_title: str, detail: str) -> str:
    """
    Cảnh báo ngắn gọn khi phát sinh lỗi lạ / đổi format API / nghi vấn lừa đảo.
    """
    return f"⚠️ CẢNH BÁO PHÁT SINH ({alert_title}): {detail}"
