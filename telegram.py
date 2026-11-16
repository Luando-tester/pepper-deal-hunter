import logging
import os
import subprocess
import tempfile

import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

# Helper Telegram đã kiểm chứng (dùng curl — urllib trực tiếp tới api.telegram.org
# bị lớp egress cắt). Dùng helper trước, fallback sang requests trực tiếp nếu
# helper không có mặt (vd chạy bản GitHub standalone với TELEGRAM_BOT_TOKEN).
TELEGRAM_HELPER = os.path.expanduser(
    "~/workspace/custom-connectors/custom.telegram/bin/telegram.py"
)
DEFAULT_CHAT_ID = "-5518467945"  # Nhóm PepperResearch — Kiếm tiền


def _send_via_helper(text: str) -> bool | None:
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
            return True
        logger.warning("[Telegram] Helper trả lỗi (rc=%s): %s", proc.returncode, proc.stderr[:200])
        return False
    except Exception as exc:
        logger.warning("[Telegram] Không chạy được helper: %s", exc)
        return None


def _send_via_requests(text: str) -> bool:
    """Fallback trực tiếp qua Bot API (cần TELEGRAM_BOT_TOKEN trong env)."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning(
            "[Telegram] Chưa cấu hình TELEGRAM_BOT_TOKEN. Nội dung:\n%s", text
        )
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID or DEFAULT_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("[Telegram] Gửi tin nhắn thất bại: %s", exc)
        return False


def send_telegram_message(text: str) -> bool:
    """
    Gửi tin nhắn qua Telegram Bot API. Không ném exception làm sập cron nếu mạng lỗi.
    """
    via_helper = _send_via_helper(text)
    if via_helper is not None:
        return via_helper
    return _send_via_requests(text)


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
    return "\n".join(lines)


def format_new_source_prompt(source_name: str, description: str) -> str:
    """
    Câu hỏi chuẩn khi phát hiện nguồn kèo mới chưa có trong danh sách quét (chờ user duyệt).
    """
    return f"Phát hiện nguồn kèo mới: {source_name} — {description}. Có thêm vào danh sách quét không?"